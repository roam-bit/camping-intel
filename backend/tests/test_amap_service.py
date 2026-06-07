"""测试 amap_service.geocode_query —— Bug 2 修复引入的高德 geocoding fallback。

为什么需要 geocode_query（而不是复用 geocode_with_amap）：
- geocode_with_amap 故意跳过 level={国家,省,市,区县} 的结果（设计给爬虫识别具体点位）
- geocode_query 服务"用户搜索词识别地理意图"，要返回市级坐标（漠河、北京等）
"""
from __future__ import annotations

import re
from unittest.mock import patch, AsyncMock

import pytest
from pytest_httpx import HTTPXMock


# ─────────────── 用例 1：成功 ───────────────

@pytest.mark.asyncio
async def test_geocode_query_success(httpx_mock: HTTPXMock):
    """高德返回有效坐标 → 返回 (lat, lon, name)。"""
    from app.services.amap_service import geocode_query

    # mock 高德返回（GCJ-02 坐标，会被转换成 WGS-84）
    httpx_mock.add_response(
        url=re.compile(r"https://restapi\.amap\.com/v3/geocode/geo.*"),
        json={
            "status": "1",
            "geocodes": [
                {
                    "location": "122.539736,53.471795",  # 漠河市 GCJ-02
                    "formatted_address": "黑龙江省大兴安岭地区漠河市",
                    "level": "市",
                }
            ],
        },
    )

    # 关键：mock cache 都 miss + mock amap_key 非空（否则 geocode_query 提前 return None）
    with patch("app.services.amap_service.cache_get", AsyncMock(return_value=None)), \
         patch("app.services.amap_service.cache_set", AsyncMock(return_value=None)), \
         patch("app.services.amap_service.amap_key", return_value="fake_key_for_test"):
        result = await geocode_query("漠河")

    assert result is not None
    lat, lon, name = result
    # WGS-84 坐标应该接近 (53.47, 122.54)（转换后偏移 < 0.01°）
    assert 53.4 < lat < 53.5, f"lat 应该在漠河附近，实际 {lat}"
    assert 122.5 < lon < 122.6, f"lon 应该在漠河附近，实际 {lon}"
    assert "漠河" in name


# ─────────────── 用例 2：高德返回 status=0 ───────────────

@pytest.mark.asyncio
async def test_geocode_query_amap_status_zero(httpx_mock: HTTPXMock):
    """高德返回 status=0（API key 错或地址无效）→ 返回 None。"""
    from app.services.amap_service import geocode_query

    httpx_mock.add_response(
        url=re.compile(r"https://restapi\.amap\.com/v3/geocode/geo.*"),
        json={"status": "0", "info": "INVALID_USER_KEY", "geocodes": []},
    )

    with patch("app.services.amap_service.cache_get", AsyncMock(return_value=None)), \
         patch("app.services.amap_service.cache_set", AsyncMock(return_value=None)), \
         patch("app.services.amap_service.amap_key", return_value="fake_key_for_test"):
        result = await geocode_query("漠河")

    assert result is None


# ─────────────── 用例 3：空 query / 空 key 防御 ───────────────

@pytest.mark.asyncio
async def test_geocode_query_empty_input():
    """空字符串 query → 直接返回 None，不调高德。"""
    from app.services.amap_service import geocode_query

    assert await geocode_query("") is None
    assert await geocode_query("   ") is None
    assert await geocode_query(None) is None  # type: ignore[arg-type]


# ─────────────── 用例 4：Cache hit（SC-007）───────────────

@pytest.mark.asyncio
async def test_geocode_query_cache_hit(httpx_mock: HTTPXMock):
    """Redis 已有缓存 → 不打高德 API，直接返回缓存值。"""
    from app.services.amap_service import geocode_query

    cached_value = {"lat": 53.471795, "lon": 122.539736, "name": "黑龙江省漠河市"}

    with patch(
        "app.services.amap_service.cache_get",
        AsyncMock(return_value=cached_value),
    ) as mock_get, patch(
        "app.services.amap_service.amap_key",
        return_value="fake_key_for_test",
    ):
        result = await geocode_query("漠河")

    assert result == (53.471795, 122.539736, "黑龙江省漠河市")
    mock_get.assert_awaited_once()
    # 关键：httpx_mock 没注册 response，如果真打了高德会触发 mock not matched 错误
    # 这条测试通过就证明 cache hit 路径没碰 httpx


# ─────────────── Key 优先级回归测试（spec 001 follow-up）───────────────
# 防止有人改 amap_key() 把 web_key 排在 rest_key 前面 ——
# 那样会导致后端 REST geocoding 用错 key 类型，返回 USERKEY_PLAT_NOMATCH

def test_amap_key_prefers_rest_over_web():
    """后端 REST geocoding 必须优先用 amap_rest_key（Web 服务 key），
    而不是 amap_web_key（Web 端 JS key），否则高德返回 USERKEY_PLAT_NOMATCH。
    """
    from app.services.amap_service import amap_key
    from app.config import settings

    # 临时设置三个 key，验证返回的是 rest_key
    original_rest = settings.amap_rest_key
    original_api = settings.amap_api_key
    original_web = settings.amap_web_key
    try:
        settings.amap_rest_key = "rest_key_for_geocoding"
        settings.amap_api_key = "api_key_fallback"
        settings.amap_web_key = "web_key_for_js_only"
        assert amap_key() == "rest_key_for_geocoding"

        # 没有 rest_key 时，fallback 顺序：api_key > web_key
        settings.amap_rest_key = ""
        assert amap_key() == "api_key_fallback"
        settings.amap_api_key = ""
        assert amap_key() == "web_key_for_js_only"  # 兜底
    finally:
        settings.amap_rest_key = original_rest
        settings.amap_api_key = original_api
        settings.amap_web_key = original_web
