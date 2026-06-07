"""信源发布时间 HTML meta 解析服务（spec-007）。

当信源 URL 路径不含日期（spec-002 兜底失败）时，对该 URL 发一次轻量 HTTP GET，
从 HTML <head> 的 meta 标签里抽真实发布时间。

优先级链（在 ai_service.attach_meta_times_to_sources 中体现）：
  URL 路径 → meta（本模块）→ citation → snippet

入口：`resolve_meta_published_at(url)` —— 永不抛异常，所有错误映射到 status。
"""
from __future__ import annotations

import asyncio
import logging
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Literal

import httpx
from pydantic import BaseModel

from app.config import settings
from app.services.cache import cache_get, cache_set, meta_time_cache_key


logger = logging.getLogger("meta_time")

META_TIME_CACHE_TTL_SECONDS = 86400  # 24h

MetaTimeStatus = Literal["matched", "timeout", "http_error", "no_meta", "error"]

# 时间合理性区间下界（露营/驻车产品的有效信源不会早于 2010）
_MIN_VALID_TIME = datetime(2010, 1, 1, tzinfo=timezone.utc)


# 进程级 HTTP 并发 semaphore（模块级单例，延迟初始化）
_HTTP_SEMAPHORE: asyncio.Semaphore | None = None


def _get_http_semaphore() -> asyncio.Semaphore:
    global _HTTP_SEMAPHORE
    if _HTTP_SEMAPHORE is None:
        _HTTP_SEMAPHORE = asyncio.Semaphore(settings.meta_time_http_concurrency)
    return _HTTP_SEMAPHORE


# 5 个 meta 标签的编译正则（按优先级顺序）；content 在 property/name/itemprop 之后
# 同时做反向顺序兜底（content 在前）
def _meta_pattern(attr: str, value: str) -> list[re.Pattern]:
    return [
        re.compile(
            rf'<meta\s+[^>]*{attr}=["\']{re.escape(value)}["\'][^>]*content=["\']([^"\']+)["\']',
            re.IGNORECASE,
        ),
        re.compile(
            rf'<meta\s+[^>]*content=["\']([^"\']+)["\'][^>]*{attr}=["\']{re.escape(value)}["\']',
            re.IGNORECASE,
        ),
    ]


# (source_tag, [正向正则, 反向正则])
_META_PATTERNS: list[tuple[str, list[re.Pattern]]] = [
    ("og:published_time", _meta_pattern("property", "og:published_time")),
    ("article:published_time", _meta_pattern("property", "article:published_time")),
    ("publishdate", _meta_pattern("name", "publishdate")),
    ("pubdate", _meta_pattern("name", "pubdate")),
    ("datePublished", _meta_pattern("itemprop", "datePublished")),
]


class MetaTimeResult(BaseModel):
    """单次 meta 时间解析的产出（data-model.md §实体 1）。"""

    url: str
    published_at: datetime | None = None
    status: MetaTimeStatus = "no_meta"
    source_tag: str | None = None
    duration_ms: int = 0
    cache_hit: bool = False
    # spec-007 C 方案：True = 走了 Playwright 渲染兜底（目标站有 JS 反爬）
    rendered: bool = False


# 进程级 Playwright 并发 semaphore（比 httpx 更重，限更严）
_PLAYWRIGHT_SEMAPHORE: asyncio.Semaphore | None = None


def _get_playwright_semaphore() -> asyncio.Semaphore:
    global _PLAYWRIGHT_SEMAPHORE
    if _PLAYWRIGHT_SEMAPHORE is None:
        _PLAYWRIGHT_SEMAPHORE = asyncio.Semaphore(settings.deep_fetch_global_concurrency)
    return _PLAYWRIGHT_SEMAPHORE


def _looks_like_antibot(status_code: int, html: str) -> bool:
    """检测响应是否是 JS 反爬挑战页（而非真实文章）。

    smzdm 等站对非浏览器返回 HTTP 202 + 极小的 probe.js 挑战页；
    真实 meta 标签只有在浏览器执行 JS 后才出现。
    """
    if status_code == 202:
        return True
    lowered = html.lower()
    # 已知反爬探针特征
    if "probe.js" in lowered or "/c2wf" in lowered or "security check" in lowered:
        return True
    # 极小 body + 有 script + body 实质为空 → JS 挑战页
    if len(html) < 3000 and "<script" in lowered and "<body></body>" in lowered.replace(" ", "").replace("\n", ""):
        return True
    return False


async def _render_html_with_playwright(url: str, timeout_seconds: float) -> str | None:
    """spec-007 C 方案：用 Playwright 渲染页面（过 JS 反爬），返回最终 HTML。

    复用 spec-006 引入的 playwright + chromium。失败返回 None。
    """
    try:
        from playwright.async_api import TimeoutError as PWTimeoutError
        from playwright.async_api import async_playwright
    except ImportError:
        return None

    async with _get_playwright_semaphore():
        try:
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(headless=True)
                context = await browser.new_context(
                    user_agent=(
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
                    ),
                )
                page = await context.new_page()
                try:
                    await page.goto(url, timeout=int(timeout_seconds * 1000), wait_until="domcontentloaded")
                    # 等 JS 反爬挑战解算完 + meta 标签注入（最多 timeout 一半）
                    await page.wait_for_timeout(min(3000, int(timeout_seconds * 500)))
                    return await page.content()
                finally:
                    await context.close()
                    await browser.close()
        except (PWTimeoutError, Exception):  # noqa: BLE001 —— 渲染失败返回 None，上游降级
            return None


def _parse_meta_time_value(raw: str) -> datetime | None:
    """宽松解析 meta content 里的时间字符串（ISO 8601 / 中文 / 通用）。"""
    raw = raw.strip()
    if not raw:
        return None
    # ISO 8601: "2026-03-15T15:41:00+08:00"
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except ValueError:
        pass
    # 中文格式: "2026年3月15日"
    m = re.match(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})", raw)
    if m:
        try:
            return datetime(int(m[1]), int(m[2]), int(m[3]), tzinfo=timezone.utc)
        except ValueError:
            pass
    # 通用 YYYY-MM-DD / YYYY/MM/DD
    m = re.search(r"(20\d{2})[-/.](\d{1,2})[-/.](\d{1,2})", raw)
    if m:
        try:
            return datetime(int(m[1]), int(m[2]), int(m[3]), tzinfo=timezone.utc)
        except ValueError:
            pass
    return None


def _is_valid_publish_time(dt: datetime) -> bool:
    """时间合理性校验：[2010-01-01, now + 1day]，防 hallucination / CMS bug。"""
    now = datetime.now(timezone.utc)
    return _MIN_VALID_TIME <= dt <= now + timedelta(days=1)


def _extract_meta_time(html: str) -> tuple[datetime | None, str | None]:
    """从 HTML 抽取发布时间，按 _META_PATTERNS 优先级。返回 (datetime, source_tag)。"""
    for source_tag, patterns in _META_PATTERNS:
        for pattern in patterns:
            m = pattern.search(html)
            if not m:
                continue
            dt = _parse_meta_time_value(m.group(1))
            if dt and _is_valid_publish_time(dt):
                return dt, source_tag
    return None, None


async def resolve_meta_published_at(
    url: str,
    *,
    http_client: httpx.AsyncClient | None = None,
    timeout_seconds: float | None = None,
) -> MetaTimeResult:
    """从信源 URL 的 HTML <head> meta 标签解析真实发布时间（contracts §1）。

    Args:
        url: 信源 URL
        http_client: 可选依赖注入（测试用）；不传则用默认 httpx.AsyncClient
        timeout_seconds: 单次 GET 超时，默认从 settings 取

    Returns:
        MetaTimeResult（永不抛异常；所有错误映射到对应 status）
    """
    timeout = timeout_seconds if timeout_seconds is not None else settings.meta_time_http_timeout
    cache_key = meta_time_cache_key(url)

    cached_raw = await cache_get(cache_key)
    if cached_raw:
        try:
            cached = MetaTimeResult.model_validate(cached_raw)
            cached.cache_hit = True
            _log_resolved(cached)
            return cached
        except Exception:  # noqa: BLE001 —— 缓存损坏当 miss
            pass

    start_t = time.perf_counter()
    published_at: datetime | None = None
    status: MetaTimeStatus = "no_meta"
    source_tag: str | None = None
    rendered = False

    try:
        async with _get_http_semaphore():
            owns_client = http_client is None
            client = http_client or httpx.AsyncClient(timeout=timeout, follow_redirects=True)
            try:
                response = await client.get(url)
                status_code = response.status_code
                html = response.text[: settings.meta_time_html_max_bytes]
            finally:
                if owns_client:
                    await client.aclose()

        # spec-007 C 方案：检测 JS 反爬挑战页 → Playwright 渲染兜底
        antibot = _looks_like_antibot(status_code, html)
        if antibot:
            rendered_html = await _render_html_with_playwright(url, settings.deep_fetch_timeout_seconds)
            if rendered_html is not None:
                rendered = True
                html = rendered_html[: settings.meta_time_html_max_bytes]
                status_code = 200  # 渲染成功，视为正常响应
            # 渲染失败则继续用 httpx 拿到的（大概率 no_meta）

        if status_code >= 400:
            status = "http_error"
        else:
            published_at, source_tag = _extract_meta_time(html)
            status = "matched" if published_at else "no_meta"
    except (httpx.TimeoutException, asyncio.TimeoutError):
        status = "timeout"
    except httpx.HTTPError:
        status = "http_error"
    except Exception:  # noqa: BLE001 —— 兜底，任何异常不让上游崩
        status = "error"

    duration_ms = int((time.perf_counter() - start_t) * 1000)
    result = MetaTimeResult(
        url=url,
        published_at=published_at,
        status=status,
        source_tag=source_tag,
        duration_ms=duration_ms,
        cache_hit=False,
        rendered=rendered,
    )

    # 所有结果（含失败）都缓存，避免反复抓死站
    try:
        import json
        await cache_set(cache_key, json.loads(result.model_dump_json()), ttl_seconds=META_TIME_CACHE_TTL_SECONDS)
    except Exception:  # noqa: BLE001
        pass

    _log_resolved(result)
    return result


def _log_resolved(result: MetaTimeResult) -> None:
    """结构化日志（contracts §7 / FR-011）。"""
    logger.info(
        "meta_time.resolved",
        extra={
            "event": "meta_time.resolved",
            "url": result.url,
            "status": result.status,
            "source_tag": result.source_tag,
            "published_at": result.published_at.isoformat() if result.published_at else None,
            "duration_ms": result.duration_ms,
            "cache_hit": result.cache_hit,
            "rendered": result.rendered,
        },
    )


# meta source_tag → sources.source_time_method 枚举值的映射
META_TAG_TO_METHOD: dict[str, str] = {
    "og:published_time": "meta_og",
    "article:published_time": "meta_article_published",
    "publishdate": "meta_publishdate",
    "pubdate": "meta_pubdate",
    "datePublished": "meta_itemprop_date",
}
