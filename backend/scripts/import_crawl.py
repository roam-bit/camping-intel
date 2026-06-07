"""spec-008 一次性导入脚本：MediaCrawler 小红书 jsonl → places/sources 库。

逐条把小红书笔记 desc 喂给现有 AI 结构化抽取（call_seed_structured），
产出干净的点位，经 geocoding 定位后入库。
- data_origin='xhs_crawl'：标记来源，可插拔（将来一条 SQL 干净删除）
- source_time 取笔记 time 字段（平台返回的精确发布时间）
- 按 note_id 判重（幂等，可重复跑）

用法：
    cd backend
    <venv>/bin/python scripts/import_crawl.py --jsonl <path>            # 正式导入
    <venv>/bin/python scripts/import_crawl.py --jsonl <path> --dry-run  # 只预演不写库
    <venv>/bin/python scripts/import_crawl.py --jsonl <path> --limit 5  # 只处理前 5 条

设计见 specs/008-mediacrawler-ingest/（contracts/import_crawl.md）。
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import httpx

# 让脚本能 import app.*（脚本在 backend/scripts/，app 在 backend/app/）
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select  # noqa: E402

from app.database import async_session  # noqa: E402
from app.models.source import Source  # noqa: E402
from app.services.ai_service import (  # noqa: E402
    call_seed_structured,
    normalize_candidates,
    upsert_ai_places,
)


XHS_NOTE_ID_RE = re.compile(r"explore/([0-9a-zA-Z]+)")
DY_AWEME_ID_RE = re.compile(r"video/([0-9]+)")


@dataclass
class ImportStats:
    """导入统计（data-model.md §实体 2）。"""

    processed: int = 0
    imported: int = 0
    unmapped: int = 0
    skipped_duplicate: int = 0
    parse_error: int = 0
    network_error: int = 0  # 重试若干次仍网络失败的瞬时错误（与脏数据区分）

    def report(self, dry_run: bool) -> str:
        prefix = "(dry-run, 未写库) " if dry_run else ""
        located = self.imported + self.unmapped
        rate = f"{round(self.imported / located * 100)}%" if located else "N/A"
        return (
            f"[导入完成] {prefix}\n"
            f"  处理总数: {self.processed}\n"
            f"  入库:     {self.imported}\n"
            f"  无法定位: {self.unmapped}\n"
            f"  跳过重复: {self.skipped_duplicate}\n"
            f"  解析错误: {self.parse_error}\n"
            f"  网络失败: {self.network_error}  (瞬时错误，重跑脚本可恢复)\n"
            f"[geocode 命中率] {self.imported} / {located} = {rate}   (SC-006 基线)"
        )


def clean_xhs_permalink(note_url_or_id: str) -> str:
    """从带 xsec_token 的小红书 note_url 或裸 note_id 算出干净 permalink。

    'xiaohongshu.com/explore/662a..?xsec_token=AB..' → 'https://www.xiaohongshu.com/explore/662a..'
    判重 key = 此函数输出（去掉每次采集都变的 xsec_token）。
    """
    text = (note_url_or_id or "").strip()
    m = XHS_NOTE_ID_RE.search(text)
    note_id = m.group(1) if m else text  # 没匹配到当作裸 note_id
    return f"https://www.xiaohongshu.com/explore/{note_id}"


def clean_douyin_permalink(aweme_url_or_id: str) -> str:
    """抖音 aweme_url 或裸 aweme_id → 干净 permalink。"""
    text = (aweme_url_or_id or "").strip()
    m = DY_AWEME_ID_RE.search(text)
    aweme_id = m.group(1) if m else text
    return f"https://www.douyin.com/video/{aweme_id}"


def _normalize_note(raw: dict) -> dict:
    """归一小红书 / 抖音 jsonl 笔记到统一字段。

    跨平台差异：小红书 note_id/note_url/time(ms)；抖音 aweme_id/aweme_url/create_time(秒)。
    抖音是视频平台，desc≈标题+话题标签，无独立 tag_list。
    """
    if "aweme_id" in raw:  # 抖音
        ct = raw.get("create_time")
        return {
            "platform": "douyin",
            "note_id": raw.get("aweme_id"),
            "title": (raw.get("title") or "").strip(),
            "desc": (raw.get("desc") or "").strip(),
            "permalink": clean_douyin_permalink(raw.get("aweme_url") or str(raw.get("aweme_id") or "")),
            "time_ms": (int(ct) * 1000) if ct else None,  # 抖音秒 → 毫秒
            "tag_list": "",
            "source_keyword": (raw.get("source_keyword") or "露营").strip(),
        }
    # 小红书
    return {
        "platform": "xhs",
        "note_id": raw.get("note_id"),
        "title": (raw.get("title") or "").strip(),
        "desc": (raw.get("desc") or "").strip(),
        "permalink": clean_xhs_permalink(raw.get("note_url") or str(raw.get("note_id") or "")),
        "time_ms": int(raw["time"]) if raw.get("time") else None,
        "tag_list": (raw.get("tag_list") or "").strip(),
        "source_keyword": (raw.get("source_keyword") or "露营").strip(),
    }


def _note_time_to_date(time_ms: object) -> str | None:
    """毫秒时间戳 → ISO 日期字符串；缺失/非法返回 None。"""
    try:
        ts = int(time_ms)  # type: ignore[arg-type]
        if ts <= 0:
            return None
        return datetime.fromtimestamp(ts / 1000, tz=timezone.utc).date().isoformat()
    except (TypeError, ValueError, OverflowError, OSError):
        return None


# 瞬时网络错误——重试可恢复，与脏数据/逻辑错区分
_TRANSIENT_ERRORS = (httpx.ConnectError, httpx.ConnectTimeout, httpx.ReadTimeout, httpx.RemoteProtocolError)
_MAX_RETRY = 3


async def _process_note_once(db, raw_note: dict, *, dry_run: bool) -> str:
    """处理一条笔记的核心逻辑（可能抛瞬时网络错误，由 _process_note 重试）。

    raw_note 是 jsonl 原始行；内部先 _normalize_note 归一小红书/抖音字段。
    """
    note = _normalize_note(raw_note)
    note_id = note["note_id"]
    if not note_id:
        return "parse_error"
    title = note["title"]
    desc = note["desc"]
    if not title and not desc:
        return "parse_error"  # 无内容可抽取

    permalink = note["permalink"]

    # 判重（AI 抽取之前，省 LLM 调用）
    exists = await db.scalar(select(Source).where(Source.source_url == permalink).limit(1))
    if exists:
        return "skipped_duplicate"

    keyword = note["source_keyword"]
    tag_list = note["tag_list"]
    answer_text = f"{title}\n{desc}\n标签：{tag_list}".strip()
    # source_time_method 按平台区分：xhs_crawl / douyin_crawl
    method = f"{note['platform']}_crawl" if note["platform"] != "xhs" else "xhs_crawl"

    # 合成 source dict（喂给 AI 抽取 + 透传字段到 Source 行）
    synthetic_source = {
        "id": "s001",
        "url": permalink,
        "domain": "xiaohongshu.com" if note["platform"] == "xhs" else "douyin.com",
        "title": title or desc[:40],
        "snippet": desc[:200],
        "published_at": _note_time_to_date(note["time_ms"]),
        "updated_at": None,
        "reliability_score": 55,  # 真人实测 UGC，给中等偏上
        "source_time_method": method,
    }

    # AI 结构化抽取
    ai_result, _meta = await call_seed_structured(keyword, answer_text, [synthetic_source], limit=3)
    spots, _unmapped = await normalize_candidates(ai_result, [synthetic_source], keyword, limit=3)

    if not spots:
        return "unmapped"

    if dry_run:
        names = ", ".join(s.get("name", "?") for s in spots)
        print(f"  [DRY-入库] {permalink} → 点位: {names}")
        return "imported"

    await upsert_ai_places(db, spots, keyword, data_origin=method)
    return "imported"


async def _process_note(db, note: dict, *, dry_run: bool) -> str:
    """处理一条笔记，返回分类：imported / unmapped / skipped_duplicate / parse_error / network_error。

    永不抛异常。瞬时网络错误重试 _MAX_RETRY 次（指数退避）；仍失败 → network_error。
    """
    for attempt in range(1, _MAX_RETRY + 1):
        try:
            return await _process_note_once(db, note, dry_run=dry_run)
        except _TRANSIENT_ERRORS as exc:
            if attempt < _MAX_RETRY:
                await asyncio.sleep(2 ** attempt)  # 2s, 4s 退避
                continue
            print(f"  [网络失败] note_id={note.get('note_id') or note.get('aweme_id')}: {type(exc).__name__}（重试 {_MAX_RETRY} 次仍失败）")
            return "network_error"
        except Exception as exc:  # noqa: BLE001 —— 非网络异常：单条隔离，不中断整批
            print(f"  [异常] note_id={note.get('note_id') or note.get('aweme_id')}: {type(exc).__name__}: {str(exc)[:120]}")
            return "parse_error"
    return "network_error"


async def import_crawl(jsonl_path: str, *, dry_run: bool = False, limit: int | None = None) -> ImportStats:
    """读 MediaCrawler jsonl → AI 抽取 → geocode → 入库。返回 ImportStats。"""
    stats = ImportStats()
    path = Path(jsonl_path).expanduser()
    if not path.exists():
        raise FileNotFoundError(f"jsonl 文件不存在: {path}")

    lines = path.read_text(encoding="utf-8").splitlines()
    if limit is not None:
        lines = lines[:limit]

    async with async_session() as db:
        for line in lines:
            line = line.strip()
            if not line:
                continue
            stats.processed += 1
            try:
                note = json.loads(line)
            except json.JSONDecodeError:
                stats.parse_error += 1
                print("  [异常] jsonl 行解析失败，跳过")
                continue
            result = await _process_note(db, note, dry_run=dry_run)
            setattr(stats, result, getattr(stats, result) + 1)

    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="spec-008 MediaCrawler 小红书数据导入")
    parser.add_argument("--jsonl", required=True, help="MediaCrawler 产出的 jsonl 文件路径")
    parser.add_argument("--dry-run", action="store_true", help="只预演不写库")
    parser.add_argument("--limit", type=int, default=None, help="只处理前 N 条（首次验证用）")
    args = parser.parse_args()

    stats = asyncio.run(import_crawl(args.jsonl, dry_run=args.dry_run, limit=args.limit))
    print(stats.report(dry_run=args.dry_run))


if __name__ == "__main__":
    main()
