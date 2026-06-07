"""spec-007 信源时间 HTML meta 解析 service 单元测试。

测试边界：用 httpx_mock 替换真实 HTTP，让 CI 不依赖外网。
覆盖：
  - test_meta_smzdm_happy_path: 含 article:published_time 的 HTML → matched
  - test_meta_no_tag_fallback: 无 meta 标签 → status=no_meta
  - test_meta_timeout_fallback: HTTP 超时 → status=timeout，不抛异常
  - test_meta_invalid_time_rejected: meta 是 2099 未来时间 → 拒绝 → no_meta
"""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from app.services.meta_time_service import (
    _extract_meta_time,
    _is_valid_publish_time,
    _parse_meta_time_value,
    resolve_meta_published_at,
)


FIXTURE_HTML = (Path(__file__).parent / "fixtures" / "meta_time_smzdm_sample.html").read_text(encoding="utf-8")


# ─────────────── happy path (US1 主测试) ───────────────

@pytest.mark.asyncio(loop_scope="session")
async def test_meta_smzdm_happy_path(httpx_mock):
    """US1 验收：含 article:published_time 的 smzdm HTML → matched + 真实日期。"""
    url = "https://post.smzdm.com/p/az8pvqqr/"
    httpx_mock.add_response(url=url, text=FIXTURE_HTML)

    with patch("app.services.meta_time_service.cache_get", AsyncMock(return_value=None)), \
         patch("app.services.meta_time_service.cache_set", AsyncMock(return_value=None)):
        result = await resolve_meta_published_at(url)

    assert result.status == "matched", f"期望 matched，实际 {result.status}"
    assert result.published_at is not None
    assert result.published_at.year == 2026
    assert result.published_at.month == 3
    assert result.published_at.day == 15
    # og:published_time 优先级高于 article:published_time，但本 fixture 两者同日期
    assert result.source_tag in ("og:published_time", "article:published_time")
    assert result.cache_hit is False


# ─────────────── no meta tag (US2) ───────────────

@pytest.mark.asyncio(loop_scope="session")
async def test_meta_no_tag_fallback(httpx_mock):
    """US2 验收：HTML 无任何已知 meta 时间标签 → status=no_meta。"""
    url = "https://example.com/no-meta-page"
    httpx_mock.add_response(url=url, text="<html><head><title>无 meta</title></head><body>正文</body></html>")

    with patch("app.services.meta_time_service.cache_get", AsyncMock(return_value=None)), \
         patch("app.services.meta_time_service.cache_set", AsyncMock(return_value=None)):
        result = await resolve_meta_published_at(url)

    assert result.status == "no_meta"
    assert result.published_at is None


# ─────────────── timeout (US2) ───────────────

@pytest.mark.asyncio(loop_scope="session")
async def test_meta_timeout_fallback(httpx_mock):
    """US2 验收：HTTP 超时 → status=timeout，不抛异常。"""
    url = "https://slow-site.example.com/article"
    httpx_mock.add_exception(httpx.TimeoutException("connection timed out"), url=url)

    with patch("app.services.meta_time_service.cache_get", AsyncMock(return_value=None)), \
         patch("app.services.meta_time_service.cache_set", AsyncMock(return_value=None)):
        result = await resolve_meta_published_at(url)

    assert result.status == "timeout"
    assert result.published_at is None


# ─────────────── invalid time rejected (US2 / FR-006) ───────────────

@pytest.mark.asyncio(loop_scope="session")
async def test_meta_invalid_time_rejected(httpx_mock):
    """FR-006：meta 标签里是 2099 未来时间 → 拒绝接受 → status=no_meta。"""
    url = "https://example.com/future-dated"
    future_html = (
        '<html><head>'
        '<meta property="og:published_time" content="2099-01-01T00:00:00+08:00">'
        '</head><body>x</body></html>'
    )
    httpx_mock.add_response(url=url, text=future_html)

    with patch("app.services.meta_time_service.cache_get", AsyncMock(return_value=None)), \
         patch("app.services.meta_time_service.cache_set", AsyncMock(return_value=None)):
        result = await resolve_meta_published_at(url)

    assert result.status == "no_meta", "未来时间应被 FR-006 拒绝"
    assert result.published_at is None


# ─────────────── http error (US2) ───────────────

@pytest.mark.asyncio(loop_scope="session")
async def test_meta_http_error(httpx_mock):
    """US2：HTTP 404 → status=http_error，不抛异常。"""
    url = "https://example.com/gone"
    httpx_mock.add_response(url=url, status_code=404, text="Not Found")

    with patch("app.services.meta_time_service.cache_get", AsyncMock(return_value=None)), \
         patch("app.services.meta_time_service.cache_set", AsyncMock(return_value=None)):
        result = await resolve_meta_published_at(url)

    assert result.status == "http_error"
    assert result.published_at is None


# ─────────────── cache hit (FR-005) ───────────────

@pytest.mark.asyncio(loop_scope="session")
async def test_meta_cache_hit(httpx_mock):
    """FR-005：缓存命中直接返回，不发 HTTP。"""
    url = "https://post.smzdm.com/p/cached/"
    cached_value = {
        "url": url,
        "published_at": "2026-03-15T15:41:00+08:00",
        "status": "matched",
        "source_tag": "og:published_time",
        "duration_ms": 100,
        "cache_hit": False,
    }

    with patch("app.services.meta_time_service.cache_get", AsyncMock(return_value=cached_value)), \
         patch("app.services.meta_time_service.cache_set", AsyncMock(return_value=None)):
        result = await resolve_meta_published_at(url)

    assert result.cache_hit is True
    assert result.status == "matched"
    # httpx_mock 没注册任何 response —— 若发了 HTTP 会报错，能通过即证明走了缓存


# ─────────────── 内部组件单测 ───────────────

def test_parse_meta_time_iso():
    dt = _parse_meta_time_value("2026-03-15T15:41:00+08:00")
    assert dt is not None and dt.year == 2026 and dt.month == 3 and dt.day == 15


def test_parse_meta_time_chinese():
    dt = _parse_meta_time_value("2026年3月15日")
    assert dt is not None and dt.month == 3 and dt.day == 15


def test_is_valid_publish_time_rejects_future_and_ancient():
    assert _is_valid_publish_time(datetime(2026, 3, 15, tzinfo=timezone.utc)) is True
    assert _is_valid_publish_time(datetime(2099, 1, 1, tzinfo=timezone.utc)) is False
    assert _is_valid_publish_time(datetime(2005, 1, 1, tzinfo=timezone.utc)) is False


def test_extract_meta_time_from_fixture():
    dt, tag = _extract_meta_time(FIXTURE_HTML)
    assert dt is not None and dt.year == 2026
    assert tag in ("og:published_time", "article:published_time")


# ─────────────── spec-007 C 方案：反爬检测 ───────────────

def test_looks_like_antibot_http_202():
    """HTTP 202 → 判定为反爬挑战页。"""
    from app.services.meta_time_service import _looks_like_antibot

    assert _looks_like_antibot(202, "<html></html>") is True


def test_looks_like_antibot_probe_js():
    """body 含 probe.js 探针特征 → 反爬。"""
    from app.services.meta_time_service import _looks_like_antibot

    probe_page = '<html><head><script src="/C2WF946J0/probe.js"></script></head><body></body></html>'
    assert _looks_like_antibot(200, probe_page) is True


def test_looks_like_antibot_normal_page():
    """正常文章页（有真实内容）→ 不是反爬。"""
    from app.services.meta_time_service import _looks_like_antibot

    assert _looks_like_antibot(200, FIXTURE_HTML) is False
