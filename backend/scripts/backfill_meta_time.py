"""spec-007 一次性回灌脚本：修历史 sources 表里的脏 source_time。

扫描 source_time 来自 citation/snippet（不可信）或 source_time_method 为 NULL 的行，
对 URL 路径不含日期的 source 重新抓 HTML meta 真实发布时间并 UPDATE。

用法：
    cd backend
    <venv>/bin/python scripts/backfill_meta_time.py            # 正式跑
    <venv>/bin/python scripts/backfill_meta_time.py --dry-run  # 只打印不写库

设计（data-model.md §回灌脚本数据流）：
- 独立连 DB（不依赖 FastAPI app）
- 候选行：source_time_method IN ('citation','snippet') OR IS NULL，且 URL 无日期段
- 按 URL 去重（同 URL 多行只抓 1 次）
- 并发由 meta_time_service 进程级 Semaphore(5) 控制
- matched → UPDATE source_time + source_time_method；其它 → 仅 UPDATE method（保留原 time）
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from collections import Counter
from pathlib import Path

# 让脚本能 import app.*（脚本在 backend/scripts/，app 在 backend/app/）
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select, update  # noqa: E402

from app.database import async_session  # noqa: E402
from app.models.source import Source  # noqa: E402
from app.services.ai_service import extract_date_from_url  # noqa: E402
from app.services.meta_time_service import (  # noqa: E402
    META_TAG_TO_METHOD,
    resolve_meta_published_at,
)


def _domain_of(url: str) -> str:
    import urllib.parse
    return urllib.parse.urlparse(url).netloc.replace("www.", "").lower()


async def backfill(dry_run: bool = False) -> None:
    async with async_session() as session:
        # 候选行：method 是 citation/snippet/NULL（未核验过的）
        # 排除 OSM/人工冷启动 —— 那些是地图数据/种子点，不是网页文章，不该抓 meta
        stmt = select(Source).where(
            Source.source_url.isnot(None),
            Source.source_type == "公开内容",
            (Source.source_time_method.in_(["citation", "snippet"]))
            | (Source.source_time_method.is_(None)),
        )
        rows = (await session.execute(stmt)).scalars().all()

        # 过滤掉 URL 路径已含日期的（那些 spec-002 已经处理对了，不需要 meta）
        candidates = [r for r in rows if r.source_url and not extract_date_from_url(r.source_url)]
        unique_urls = sorted({r.source_url for r in candidates if r.source_url})

        print(f"[扫描] {len(candidates)} candidate rows / {len(unique_urls)} unique urls")
        if not unique_urls:
            print("[完成] 无候选数据，无需回灌")
            return

        # 并发抓取（Semaphore 在 meta_time_service 内部）
        results = await asyncio.gather(
            *[resolve_meta_published_at(url) for url in unique_urls]
        )
        url_to_result = dict(zip(unique_urls, results))

        status_counter: Counter = Counter()
        domain_success: Counter = Counter()
        domain_total: Counter = Counter()
        updated_rows = 0

        for url, result in url_to_result.items():
            status_counter[result.status] += 1
            dom = _domain_of(url)
            domain_total[dom] += 1
            if result.status == "matched":
                domain_success[dom] += 1

        # 写库：每个候选行按其 URL 的解析结果 UPDATE
        nulled_rows = 0
        for row in candidates:
            result = url_to_result.get(row.source_url)
            if not result:
                continue
            if result.status == "matched" and result.published_at:
                method = META_TAG_TO_METHOD.get(result.source_tag or "", "meta_og")
                if dry_run:
                    print(f"  [DRY-修正] {row.source_url} → {result.published_at.date()} ({method})")
                else:
                    await session.execute(
                        update(Source)
                        .where(Source.id == row.id)
                        .values(source_time=result.published_at, source_time_method=method)
                    )
                updated_rows += 1
            elif row.source_time is not None:
                # spec-007 止血：候选行 URL 无日期但有 source_time → 该时间必来自
                # citation/snippet 启发式（spec-002 仅这两个 fallback）→ 不可靠。
                # meta 又抓不到 → 置空错日期，标 unverified。
                if dry_run:
                    print(f"  [DRY-置空] {row.source_url} 原 {row.source_time} → NULL（{result.status}）")
                else:
                    await session.execute(
                        update(Source)
                        .where(Source.id == row.id)
                        .values(source_time=None, source_time_method="unverified")
                    )
                nulled_rows += 1
            else:
                # source_time 本来就是 NULL → 仅标 method 记录已尝试过
                if not dry_run:
                    await session.execute(
                        update(Source)
                        .where(Source.id == row.id)
                        .values(source_time_method="unverified")
                    )

        if not dry_run:
            await session.commit()

        # 报告
        print("[结果]")
        for st in ("matched", "no_meta", "http_error", "timeout", "error"):
            if status_counter.get(st):
                print(f"  {st}: {status_counter[st]}")
        prefix = "(dry-run, 未写库) " if dry_run else ""
        print(f"[DB UPDATE] {prefix}{updated_rows} 条 source_time 被 meta 修正、{nulled_rows} 条错日期被置空（标 unverified）")
        print("[域名 top 10 成功率]")
        for dom, total in domain_total.most_common(10):
            ok = domain_success.get(dom, 0)
            pct = round(ok / total * 100) if total else 0
            print(f"  {dom}  {ok}/{total} ({pct}%)")


def main() -> None:
    parser = argparse.ArgumentParser(description="spec-007 信源时间回灌脚本")
    parser.add_argument("--dry-run", action="store_true", help="只打印将要做的 UPDATE，不实际写库")
    args = parser.parse_args()
    asyncio.run(backfill(dry_run=args.dry_run))


if __name__ == "__main__":
    main()
