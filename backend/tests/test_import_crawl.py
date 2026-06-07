"""spec-008 MediaCrawler 导入脚本测试。

测试边界：mock call_seed_structured / normalize_candidates / upsert_ai_places，
不调真实 Ark / 高德 / 不依赖真实小红书数据。
覆盖：
  - test_clean_xhs_permalink: 带 xsec_token 的 URL → 干净 permalink
  - test_import_crawl_happy_path: 可定位笔记 → imported，字段映射正确
  - test_import_crawl_idempotent: 同笔记跑两次 → 第二次 skipped_duplicate
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

# 让测试能 import scripts.import_crawl
_BACKEND = Path(__file__).resolve().parent.parent
if str(_BACKEND) not in sys.path:
    sys.path.insert(0, str(_BACKEND))

from scripts.import_crawl import (  # noqa: E402
    clean_douyin_permalink,
    clean_xhs_permalink,
    _normalize_note,
    _note_time_to_date,
    _process_note,
)


FIXTURE = Path(__file__).parent / "fixtures" / "crawl_xhs_sample.jsonl"


# ─────────────── clean_xhs_permalink ───────────────

def test_clean_xhs_permalink_strips_xsec_token():
    """带 xsec_token 的 URL → 干净 permalink，不含 query。"""
    url = "https://www.xiaohongshu.com/explore/662a6ef2?xsec_token=ABdef&xsec_source=pc_search"
    assert clean_xhs_permalink(url) == "https://www.xiaohongshu.com/explore/662a6ef2"


def test_clean_xhs_permalink_bare_id():
    """裸 note_id → 拼成 permalink。"""
    assert clean_xhs_permalink("aaaa1111") == "https://www.xiaohongshu.com/explore/aaaa1111"


def test_clean_xhs_permalink_idempotent():
    """对干净 URL 再处理 → 不变（判重 key 稳定）。"""
    clean = "https://www.xiaohongshu.com/explore/xyz"
    assert clean_xhs_permalink(clean) == clean


def test_note_time_to_date():
    """毫秒时间戳 → ISO 日期；非法 → None。"""
    assert _note_time_to_date(1714056946000) == "2024-04-25"
    assert _note_time_to_date(0) is None
    assert _note_time_to_date(None) is None
    assert _note_time_to_date("bad") is None


# ─────────────── 多平台归一（抖音）───────────────

def test_clean_douyin_permalink():
    """抖音 aweme_url / 裸 aweme_id → 干净 permalink。"""
    url = "https://www.douyin.com/video/7642004354572776399"
    assert clean_douyin_permalink(url) == url
    assert clean_douyin_permalink("7642004354572776399") == url


def test_normalize_note_xhs():
    """小红书 jsonl → 统一字段（time 毫秒原样）。"""
    raw = {"note_id": "abc", "title": "t", "desc": "d", "time": 1714056946000,
           "note_url": "https://www.xiaohongshu.com/explore/abc?xsec_token=X", "source_keyword": "露营"}
    n = _normalize_note(raw)
    assert n["platform"] == "xhs"
    assert n["note_id"] == "abc"
    assert n["permalink"] == "https://www.xiaohongshu.com/explore/abc"
    assert n["time_ms"] == 1714056946000


def test_normalize_note_douyin():
    """抖音 jsonl → 统一字段：aweme_id→note_id、create_time(秒)→time_ms(毫秒)。"""
    raw = {"aweme_id": "7642004354572776399", "title": "营地", "desc": "免费露营",
           "create_time": 1779323100, "aweme_url": "https://www.douyin.com/video/7642004354572776399",
           "source_keyword": "免费露营"}
    n = _normalize_note(raw)
    assert n["platform"] == "douyin"
    assert n["note_id"] == "7642004354572776399"
    assert n["permalink"] == "https://www.douyin.com/video/7642004354572776399"
    assert n["time_ms"] == 1779323100 * 1000  # 秒 → 毫秒


# ─────────────── _process_note ───────────────

@pytest.mark.asyncio(loop_scope="session")
async def test_process_note_parse_error_missing_note_id():
    """缺 note_id 的笔记 → parse_error。"""
    db = AsyncMock()
    note = {"title": "x", "desc": "y", "note_url": ""}
    result = await _process_note(db, note, dry_run=True)
    assert result == "parse_error"


@pytest.mark.asyncio(loop_scope="session")
async def test_process_note_happy_path_imported():
    """可定位笔记 → imported（mock AI 抽取返回 1 个 spot）。"""
    db = AsyncMock()
    db.scalar = AsyncMock(return_value=None)  # 判重：不存在
    note = {
        "note_id": "aaaa1111",
        "title": "莫干山西坡免费露营地",
        "desc": "德清县莫干山镇高峰村，开车直达溪边",
        "time": 1714056946000,
        "tag_list": "莫干山,德清露营",
        "note_url": "https://www.xiaohongshu.com/explore/aaaa1111?xsec_token=ABx",
        "source_keyword": "免费露营",
    }
    fake_spot = {"name": "莫干山西坡露营地", "status": "pending_review"}

    with patch("scripts.import_crawl.call_seed_structured", AsyncMock(return_value=({"spots": [fake_spot]}, {}))), \
         patch("scripts.import_crawl.normalize_candidates", AsyncMock(return_value=([fake_spot], []))), \
         patch("scripts.import_crawl.upsert_ai_places", AsyncMock(return_value=None)) as mock_upsert:
        result = await _process_note(db, note, dry_run=False)

    assert result == "imported"
    # 验证 upsert 被调用且 data_origin='xhs_crawl'
    mock_upsert.assert_awaited_once()
    assert mock_upsert.call_args.kwargs.get("data_origin") == "xhs_crawl"


@pytest.mark.asyncio(loop_scope="session")
async def test_process_note_unmapped_when_no_spots():
    """AI 抽取定位不到具体地名（spots 为空）→ unmapped。"""
    db = AsyncMock()
    db.scalar = AsyncMock(return_value=None)
    note = {
        "note_id": "bbbb2222",
        "title": "广东露营合集",
        "desc": "广东几个露营地",
        "time": 1717000000000,
        "note_url": "https://www.xiaohongshu.com/explore/bbbb2222?xsec_token=ABy",
        "source_keyword": "免费露营",
    }
    with patch("scripts.import_crawl.call_seed_structured", AsyncMock(return_value=({"spots": []}, {}))), \
         patch("scripts.import_crawl.normalize_candidates", AsyncMock(return_value=([], []))):
        result = await _process_note(db, note, dry_run=False)

    assert result == "unmapped"


@pytest.mark.asyncio(loop_scope="session")
async def test_process_note_idempotent_skip_duplicate():
    """note 对应 source_url 已存在 → skipped_duplicate（不调 AI）。"""
    db = AsyncMock()
    db.scalar = AsyncMock(return_value=object())  # 判重：已存在
    note = {
        "note_id": "aaaa1111",
        "title": "莫干山露营",
        "desc": "x",
        "note_url": "https://www.xiaohongshu.com/explore/aaaa1111?xsec_token=ABz",
        "source_keyword": "免费露营",
    }
    with patch("scripts.import_crawl.call_seed_structured", AsyncMock()) as mock_ai:
        result = await _process_note(db, note, dry_run=False)

    assert result == "skipped_duplicate"
    # 关键：判重命中后不该调 AI 抽取
    mock_ai.assert_not_awaited()
