"""spec-006 微头条话题页深抓 service 单元测试。

测试边界：用 FakeFetcher 替换 Playwright，让 CI 不依赖真浏览器。
覆盖：
  - test_deep_fetch_happy_path: 候选集含相关帖 → matched + 命中预期单帖
  - test_deep_fetch_timeout_fallback: fetcher 抛 TimeoutError → match_status=timeout，无异常
  - test_deep_fetch_no_match: 候选集全无关键词 → match_status=no_match
  - test_deep_fetch_cache_hit: 第二次调用同 url+keyword 直接走缓存
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from app.services.deep_fetch_service import (
    fetch_and_match,
    pick_top_relevant,
)
from app.services.fetchers.base import FetcherError, TopicPagePost


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "toutiao_topic_page.json"


def _load_fixture_posts() -> list[TopicPagePost]:
    """从 JSON fixture 加载成 TopicPagePost 列表。"""
    data = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    posts: list[TopicPagePost] = []
    for item in data["posts"]:
        published_at = (
            datetime.fromisoformat(item["published_at"]) if item.get("published_at") else None
        )
        posts.append(TopicPagePost(
            title=item["title"],
            text_excerpt=item["text_excerpt"],
            published_at=published_at,
            permalink_url=item["permalink_url"],
        ))
    return posts


class FakeFetcher:
    """测试用 PostFetcher 实现；预设 fetch 行为（返回列表 / 抛超时 / 抛错）。"""

    def __init__(self, posts: list[TopicPagePost] | None = None, *, raise_exc: Exception | None = None):
        self._posts = posts or []
        self._raise_exc = raise_exc
        self.call_count = 0

    async def fetch(self, topic_url: str, *, timeout_seconds: float = 15.0) -> list[TopicPagePost]:
        self.call_count += 1
        if self._raise_exc:
            raise self._raise_exc
        return self._posts


# ─────────────── happy path (US1 主测试) ───────────────

@pytest.mark.asyncio
async def test_deep_fetch_happy_path():
    """US1 验收 1：fixture 含 3 条莫干山帖 + 2 条无关 → 返回 matched + score≥threshold。

    用 keyword_only fallback 路径（无 Ark key 时自动降级），不调用真 LLM；
    L1 过滤会把 3 条莫干山帖留下，fallback 取第一条。
    """
    posts = _load_fixture_posts()
    fetcher = FakeFetcher(posts=posts)

    # patch cache 全 miss，避免污染上次跑的缓存
    with patch("app.services.deep_fetch_service.cache_get", AsyncMock(return_value=None)), \
         patch("app.services.deep_fetch_service.cache_set", AsyncMock(return_value=None)):
        result = await fetch_and_match(
            "https://weitoutiao.zjurl.cn/topic/free_camping",
            "莫干山",
            fetcher=fetcher,
            relevance_threshold=0.5,
        )

    assert result.match_status == "matched", f"期望 matched，实际 {result.match_status}"
    assert result.matched_post is not None
    assert "莫干山" in result.matched_post.title, f"命中帖标题应含莫干山，实际: {result.matched_post.title}"
    assert result.posts_extracted == 5
    assert result.cache_hit is False
    assert fetcher.call_count == 1
    assert result.duration_ms >= 0


# ─────────────── timeout regression (US2 主测试) ───────────────

@pytest.mark.asyncio
async def test_deep_fetch_timeout_fallback():
    """US2 验收 2：fetcher 抛 asyncio.TimeoutError → match_status=timeout，不抛异常。"""
    fetcher = FakeFetcher(raise_exc=asyncio.TimeoutError("Playwright 超时"))

    with patch("app.services.deep_fetch_service.cache_get", AsyncMock(return_value=None)), \
         patch("app.services.deep_fetch_service.cache_set", AsyncMock(return_value=None)):
        result = await fetch_and_match(
            "https://weitoutiao.zjurl.cn/topic/some_topic",
            "莫干山",
            fetcher=fetcher,
        )

    assert result.match_status == "timeout"
    assert result.matched_post is None
    assert result.posts_extracted == 0
    assert fetcher.call_count == 1


# ─────────────── no_match (US2 补充测试) ───────────────

@pytest.mark.asyncio
async def test_deep_fetch_no_match():
    """US2 验收 1：候选集无任何相关帖 → match_status=no_match。

    fixture 里只有西藏 + 长白山的 2 条与「莫干山」无关 → 经 L1 字面过滤后候选集为空。
    """
    all_posts = _load_fixture_posts()
    # 只取后 2 条不含莫干山的帖
    posts = [p for p in all_posts if "莫干山" not in p.title and "莫干山" not in p.text_excerpt]
    assert len(posts) == 2, "fixture 应该有 2 条无关帖"
    fetcher = FakeFetcher(posts=posts)

    with patch("app.services.deep_fetch_service.cache_get", AsyncMock(return_value=None)), \
         patch("app.services.deep_fetch_service.cache_set", AsyncMock(return_value=None)):
        result = await fetch_and_match(
            "https://weitoutiao.zjurl.cn/topic/all_irrelevant",
            "莫干山",
            fetcher=fetcher,
        )

    assert result.match_status == "no_match"
    assert result.matched_post is None
    assert result.posts_extracted == 2


# ─────────────── fetcher error (US2 补充测试) ───────────────

@pytest.mark.asyncio
async def test_deep_fetch_fetcher_error_fallback():
    """fetcher 抛 FetcherError（非 timeout）→ match_status=error，不抛异常。"""
    fetcher = FakeFetcher(raise_exc=FetcherError("微头条 SPA 解析失败"))

    with patch("app.services.deep_fetch_service.cache_get", AsyncMock(return_value=None)), \
         patch("app.services.deep_fetch_service.cache_set", AsyncMock(return_value=None)):
        result = await fetch_and_match(
            "https://weitoutiao.zjurl.cn/topic/broken_page",
            "莫干山",
            fetcher=fetcher,
        )

    assert result.match_status == "error"
    assert result.matched_post is None


# ─────────────── cache hit (FR-012) ───────────────

@pytest.mark.asyncio
async def test_deep_fetch_cache_hit_returns_cached():
    """第二次调用同 url+keyword → 直接命中缓存，cache_hit=True，不调 fetcher。"""
    posts = _load_fixture_posts()
    fetcher = FakeFetcher(posts=posts)
    cached_value = {
        "source_url": "https://weitoutiao.zjurl.cn/topic/cached",
        "keyword": "莫干山",
        "matched_post": {
            "title": "缓存里的莫干山帖",
            "text_excerpt": "this is from cache",
            "published_at": None,
            "permalink_url": "https://weitoutiao.zjurl.cn/article/cached999",
        },
        "top_score": 0.85,
        "match_status": "matched",
        "duration_ms": 100,
        "posts_extracted": 5,
        "fallback_mode": "none",
        "cache_hit": False,
    }

    with patch("app.services.deep_fetch_service.cache_get", AsyncMock(return_value=cached_value)), \
         patch("app.services.deep_fetch_service.cache_set", AsyncMock(return_value=None)):
        result = await fetch_and_match(
            "https://weitoutiao.zjurl.cn/topic/cached",
            "莫干山",
            fetcher=fetcher,
        )

    assert result.cache_hit is True
    assert result.match_status == "matched"
    assert result.matched_post is not None
    assert result.matched_post.permalink_url == "https://weitoutiao.zjurl.cn/article/cached999"
    # 关键：fetcher 没被调用
    assert fetcher.call_count == 0


# ─────────────── 内部组件测试 ───────────────

@pytest.mark.asyncio
async def test_pick_top_relevant_empty_posts():
    """空 list 输入 → no_match。"""
    result = await pick_top_relevant([], "莫干山", threshold=0.6)
    assert result == (None, 0.0, "no_match", "none")


@pytest.mark.asyncio
async def test_pick_top_relevant_single_candidate_skip_llm():
    """L1 过滤后候选集 == 1 → 跳过 LLM，直接返回 score=1.0。"""
    posts = [
        TopicPagePost(title="莫干山露营", text_excerpt="去过", published_at=None, permalink_url="https://x.com/a"),
        TopicPagePost(title="云南旅行", text_excerpt="不相关", published_at=None, permalink_url="https://x.com/b"),
    ]
    result = await pick_top_relevant(posts, "莫干山", threshold=0.6)
    matched, score, status, fallback = result
    assert status == "matched"
    assert matched is not None
    assert "莫干山" in matched.title
    assert score == 1.0
    assert fallback == "none"


def test_cache_key_consistency():
    """同 (url, keyword) 多次调用应得到相同 key（FR-012）。"""
    from app.services.cache import deep_fetch_cache_key

    k1 = deep_fetch_cache_key("https://weitoutiao.zjurl.cn/topic/x", "莫干山")
    k2 = deep_fetch_cache_key("https://weitoutiao.zjurl.cn/topic/x", "莫干山")
    assert k1 == k2
    assert k1.startswith("deep_fetch:v1:")
    # NFKC 归一：「莫干山 」（带空格）和「莫干山」 命中同一 key
    k3 = deep_fetch_cache_key("https://weitoutiao.zjurl.cn/topic/x", "莫干山 ")
    assert k1 == k3
