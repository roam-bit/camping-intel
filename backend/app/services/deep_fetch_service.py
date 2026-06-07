"""信源深度抓取服务（spec-006 Phase 1 主入口）。

对识别为「微头条话题页」的信源 URL 调用：
  1. PostFetcher 渲染并抽取页内候选单帖（list[TopicPagePost]）
  2. pick_top_relevant() 用 L1 字面匹配 + L2 Ark LLM 评分筛 Top 1
  3. 命中：返回单帖 permalink；未命中/超时/错误：返回 None + 状态码
  4. 全程 Redis 缓存 24h（key 由 deep_fetch_cache_key 生成）
  5. 进程级 Semaphore(3) 全局限流，避免多用户同时搜索时 Playwright 资源耗尽

调用入口：`fetch_and_match(topic_url, keyword, *, fetcher=None)`
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
import unicodedata
from typing import Literal

import httpx
from pydantic import BaseModel

from app.config import settings
from app.services.cache import cache_get, cache_set, deep_fetch_cache_key
from app.services.fetchers.base import FetcherError, PostFetcher, TopicPagePost


logger = logging.getLogger("deep_fetch")

DEEP_FETCH_CACHE_TTL_SECONDS = 86400  # 24h


# 进程级全局并发 semaphore（模块级单例）；按 settings 配置初始化
_GLOBAL_SEMAPHORE: asyncio.Semaphore | None = None


def _get_global_semaphore() -> asyncio.Semaphore:
    """延迟初始化避免模块导入期就消耗 asyncio event loop。"""
    global _GLOBAL_SEMAPHORE
    if _GLOBAL_SEMAPHORE is None:
        _GLOBAL_SEMAPHORE = asyncio.Semaphore(settings.deep_fetch_global_concurrency)
    return _GLOBAL_SEMAPHORE


MatchStatus = Literal["matched", "no_match", "timeout", "error"]
FallbackMode = Literal["none", "keyword_only"]


class TopicPostDict(BaseModel):
    """TopicPagePost 的 Pydantic 镜像，便于 JSON 序列化进 Redis。"""

    title: str
    text_excerpt: str
    published_at: str | None = None  # ISO 字符串；缓存里不存原 datetime
    permalink_url: str

    @classmethod
    def from_dataclass(cls, post: TopicPagePost) -> "TopicPostDict":
        return cls(
            title=post.title,
            text_excerpt=post.text_excerpt,
            published_at=post.published_at.isoformat() if post.published_at else None,
            permalink_url=post.permalink_url,
        )


class DeepFetchResult(BaseModel):
    """单次深抓的完整产出（data-model.md §实体 2）。"""

    source_url: str
    keyword: str
    matched_post: TopicPostDict | None = None
    top_score: float = 0.0
    match_status: MatchStatus = "no_match"
    duration_ms: int = 0
    posts_extracted: int = 0
    fallback_mode: FallbackMode = "none"
    cache_hit: bool = False


def _normalize_keyword(keyword: str) -> str:
    return unicodedata.normalize("NFKC", keyword).strip().lower()


async def _score_with_ark(candidates: list[TopicPagePost], keyword: str) -> tuple[int | None, float, FallbackMode]:
    """用 Ark LLM 对候选集打分，返回 (index, score, fallback_mode)。

    L2 评分（research.md D2）：
    - 候选集 = 1: 调用方应已直接返回，这里防御性 return (0, 1.0, "none")
    - 候选集 >= 2: 调 Ark Responses API，prompt 严格要求 JSON {post_id, score}
    - 任意失败（超时/JSON 解析/post_id 越界）: 降级返回 (0, 1.0, "keyword_only")

    LLM timeout 5s（fail-fast）—— 不让评分卡死整个深抓。
    """
    if not candidates:
        return (None, 0.0, "none")
    if len(candidates) == 1:
        return (0, 1.0, "none")

    # 构造 prompt，限制 token：每条只取 title + 前 200 字 excerpt
    items_text = "\n".join(
        f"[{i}] 标题: {c.title}\n    正文: {c.text_excerpt[:200]}"
        for i, c in enumerate(candidates)
    )
    prompt = (
        f"用户搜索的关键词是「{keyword}」。下面是若干候选帖子，请从中挑出与该关键词"
        f"最相关的 1 条（语义相关，不仅看字面），并给出 0-1 的相关性分数。\n\n"
        f"{items_text}\n\n"
        f"严格按 JSON 输出，不要多余文字：{{\"post_id\": <整数 0 到 {len(candidates)-1}>, \"score\": <0-1 浮点>}}"
    )
    payload = {
        "model": settings.ark_model,
        "input": [{"role": "user", "content": prompt}],
        "max_output_tokens": 100,
    }

    if not settings.ark_api_key:
        # 无 key → 降级 keyword_only
        return (0, 1.0, "keyword_only")

    try:
        headers = {"Authorization": f"Bearer {settings.ark_api_key}", "Content-Type": "application/json"}
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(settings.ark_api_url, headers=headers, json=payload)
            if response.status_code >= 400:
                return (0, 1.0, "keyword_only")
            result = response.json()
        # 解析 Ark Responses API 输出
        text = ""
        for item in result.get("output", []):
            if item.get("type") == "message":
                for block in item.get("content", []):
                    if block.get("type") == "output_text":
                        text += block.get("text", "")
        text = text.strip()
        # 去掉可能的 markdown 围栏
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(line for line in lines if not line.startswith("```"))
        data = json.loads(text)
        post_id = int(data["post_id"])
        score = float(data["score"])
        if not (0 <= post_id < len(candidates)):
            return (0, 1.0, "keyword_only")
        return (post_id, max(0.0, min(1.0, score)), "none")
    except (asyncio.TimeoutError, httpx.HTTPError, json.JSONDecodeError, KeyError, ValueError, TypeError):
        return (0, 1.0, "keyword_only")


async def pick_top_relevant(
    posts: list[TopicPagePost],
    keyword: str,
    *,
    threshold: float,
) -> tuple[TopicPagePost | None, float, MatchStatus, FallbackMode]:
    """L1 字面匹配 + L2 Ark 评分（contracts §3）。

    Returns:
        (matched_post, top_score, match_status, fallback_mode)
        match_status ∈ {"matched", "no_match"}
        timeout/error 在 fetch_and_match 上层判定，这里只关心相关性
    """
    if not posts:
        return (None, 0.0, "no_match", "none")
    keyword_norm = _normalize_keyword(keyword)
    candidates = [
        p for p in posts
        if keyword_norm in f"{p.title}\n{p.text_excerpt}".lower()
    ]
    if not candidates:
        return (None, 0.0, "no_match", "none")

    index, score, fallback_mode = await _score_with_ark(candidates, keyword)
    if index is None:
        return (None, 0.0, "no_match", "none")
    if score < threshold and fallback_mode == "none":
        # LLM 给出明确低分 → 真的不相关
        return (None, score, "no_match", "none")
    return (candidates[index], score, "matched", fallback_mode)


async def fetch_and_match(
    topic_url: str,
    keyword: str,
    *,
    fetcher: PostFetcher | None = None,
    relevance_threshold: float | None = None,
    timeout_seconds: float | None = None,
) -> DeepFetchResult:
    """对一个话题页 URL 触发深抓 + 关键词筛选（contracts §1）。

    Args:
        topic_url: 已被 is_topic_aggregator_url 判定为话题页的 URL
        keyword: 用户搜索关键词
        fetcher: 可选依赖注入（测试用 FakeFetcher）；不传则用 ToutiaoPlaywrightFetcher
        relevance_threshold: 默认从 settings 取
        timeout_seconds: Playwright 单页渲染超时；默认从 settings 取

    Returns:
        DeepFetchResult（永不抛异常；所有错误都映射到 match_status=error 或 timeout）
    """
    threshold = relevance_threshold if relevance_threshold is not None else settings.deep_fetch_relevance_threshold
    timeout = timeout_seconds if timeout_seconds is not None else settings.deep_fetch_timeout_seconds

    cache_key = deep_fetch_cache_key(topic_url, keyword)
    cached_raw = await cache_get(cache_key)
    if cached_raw:
        try:
            cached = DeepFetchResult.model_validate(cached_raw)
            cached.cache_hit = True
            _log_completed(cached)
            return cached
        except Exception:
            # 缓存值损坏 → 当 miss 处理
            pass

    start_t = time.perf_counter()

    # 默认 fetcher：延迟导入避免循环
    if fetcher is None:
        from app.services.fetchers.toutiao_fetcher import ToutiaoPlaywrightFetcher
        fetcher = ToutiaoPlaywrightFetcher()

    posts: list[TopicPagePost] = []
    match_status: MatchStatus = "no_match"
    matched_post: TopicPagePost | None = None
    top_score = 0.0
    fallback_mode: FallbackMode = "none"

    try:
        async with _get_global_semaphore():
            posts = await fetcher.fetch(topic_url, timeout_seconds=timeout)
        matched_post, top_score, match_status, fallback_mode = await pick_top_relevant(
            posts, keyword, threshold=threshold
        )
    except asyncio.TimeoutError:
        match_status = "timeout"
    except FetcherError:
        match_status = "error"
    except Exception:  # noqa: BLE001 —— 兜底；任何未预期异常都不让上游崩
        match_status = "error"

    duration_ms = int((time.perf_counter() - start_t) * 1000)

    result = DeepFetchResult(
        source_url=topic_url,
        keyword=keyword,
        matched_post=TopicPostDict.from_dataclass(matched_post) if matched_post else None,
        top_score=top_score,
        match_status=match_status,
        duration_ms=duration_ms,
        posts_extracted=len(posts),
        fallback_mode=fallback_mode,
        cache_hit=False,
    )

    # 所有结果（含失败）都缓存（research.md D3：避免坏话题页被反复抓）
    try:
        await cache_set(cache_key, json.loads(result.model_dump_json()), ttl_seconds=DEEP_FETCH_CACHE_TTL_SECONDS)
    except Exception:  # noqa: BLE001
        pass

    _log_completed(result)
    return result


def _log_completed(result: DeepFetchResult) -> None:
    """输出结构化日志（contracts §5 / FR-008）。

    走 extra={} 模式 → 由 app.utils.logger.JsonFormatter 把 extra 字段合到主 JSON 里，
    一条日志一个 JSON 对象，不嵌套，便于 jq/Grafana 解析。
    """
    logger.info(
        "deep_fetch.completed",
        extra={
            "event": "deep_fetch.completed",
            "url": result.source_url,
            "keyword": result.keyword,
            "match_status": result.match_status,
            "top_score": round(result.top_score, 3),
            "duration_ms": result.duration_ms,
            "posts_extracted": result.posts_extracted,
            "fallback_mode": result.fallback_mode,
            "cache_hit": result.cache_hit,
        },
    )
