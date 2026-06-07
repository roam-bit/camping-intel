"""AI pipeline 单元测试：不依赖外部 Ark/高德调用，纯函数级验证。"""
from __future__ import annotations

import pytest
from pytest_httpx import HTTPXMock

from app.services.ai_service import cache_key

# 注：本文件有同步 + async 混合测试，async 测试单独用 @pytest.mark.asyncio mark
# 避免文件级 pytestmark 给同步测试也加 asyncio 导致 warning


def test_cache_key_stable_for_same_input():
    """同 (query, limit, radius) 多次调用应得到相同 key"""
    k1 = cache_key("杭州周边露营", 12, 80)
    k2 = cache_key("杭州周边露营", 12, 80)
    assert k1 == k2


def test_cache_key_changes_with_query():
    """不同 query 应得到不同 key（防缓存串）"""
    k1 = cache_key("杭州周边露营", 12, 80)
    k2 = cache_key("舟山周边露营", 12, 80)
    assert k1 != k2


def test_cache_key_uses_cache_prefix_safe():
    """key 应是 hex 字符串（hashlib.sha256），不含特殊字符"""
    k = cache_key("test", 5, 50)
    assert all(c in "0123456789abcdef" for c in k), f"key 应为纯 hex: {k}"
    assert len(k) == 64  # sha256 hex


@pytest.mark.asyncio(loop_scope="session")
async def test_normalize_candidates_threshold_excludes_zero_source(monkeypatch):
    """P0-3 阈值: 0 信源候选应被踢到 unmapped_candidates 而非 spots"""
    from app.services.ai_service import normalize_candidates

    # mock：1 个 candidate 含 source_ids，1 个不含
    ai_result = {
        "spots": [
            {"name": "测试营地A", "source_ids": ["s001"], "lat": 30.27, "lon": 120.15, "type": "营地"},
            # 无 source_ids 的候选：normalize_candidates line 742 if not source_ids -> continue
            {"name": "测试营地B", "source_ids": [], "lat": 30.28, "lon": 120.16, "type": "营地"},
        ],
        "unmapped_candidates": [],
    }
    sources = [{"id": "s001", "url": "https://example.com/article1", "title": "测试文章", "domain": "example.com"}]
    spots, unmapped = await normalize_candidates(ai_result, sources, query="测试", limit=10)
    # A 有 1 信源 → cred=50 进 pending_review (spots)
    # B 无 source_ids → 直接被 line 742 continue 掉，既不进 spots 也不进 unmapped
    assert any(s["name"] == "测试营地A" for s in spots), "1 信源候选应在 spots 内"
    assert all(s["name"] != "测试营地B" for s in spots), "0 信源候选不应在 spots 内"


@pytest.mark.asyncio(loop_scope="session")
async def test_normalize_candidates_credibility_formula():
    """P0-3 临时公式: 1 信源=50, 2 信源=75, 3+ 信源=100"""
    from app.services.ai_service import normalize_candidates

    sources = [
        {"id": "s001", "url": "https://example.com/a1", "title": "A1", "domain": "example.com"},
        {"id": "s002", "url": "https://example.com/a2", "title": "A2", "domain": "example.com"},
        {"id": "s003", "url": "https://example.com/a3", "title": "A3", "domain": "example.com"},
    ]
    ai_result = {
        "spots": [
            {"name": "S1", "source_ids": ["s001"], "lat": 30.27, "lon": 120.15, "type": "营地"},
            {"name": "S2", "source_ids": ["s001", "s002"], "lat": 30.28, "lon": 120.16, "type": "营地"},
            {"name": "S3", "source_ids": ["s001", "s002", "s003"], "lat": 30.29, "lon": 120.17, "type": "营地"},
        ]
    }
    spots, _ = await normalize_candidates(ai_result, sources, query="测试", limit=10)
    by_name = {s["name"]: s for s in spots}
    assert by_name["S1"]["credibility_score"] == 50
    assert by_name["S1"]["status"] == "pending_review"
    assert by_name["S2"]["credibility_score"] == 75
    assert by_name["S2"]["status"] == "active"
    assert by_name["S3"]["credibility_score"] == 100
    assert by_name["S3"]["status"] == "active"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# spec 002-fix-source-date：信源发布时间显示准确性修复
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# T001 [US1] URL 路径抽日期 ─────────────────────

def test_extract_date_from_url_renmin_yyyy_mmdd():
    """人民网 /n/2024/1108/c-xxx 格式"""
    from app.services.ai_service import extract_date_from_url
    d = extract_date_from_url("https://sh.people.com.cn/n/2024/1108/c134768-xxx.html")
    assert d is not None
    assert (d.year, d.month, d.day) == (2024, 11, 8)


def test_extract_date_from_url_tencent_yyyymmdd():
    """腾讯新闻 /a/20260512A04QJ500 格式"""
    from app.services.ai_service import extract_date_from_url
    d = extract_date_from_url("https://news.qq.com/rain/a/20260512A04QJ500")
    assert d is not None
    assert (d.year, d.month, d.day) == (2026, 5, 12)


def test_extract_date_from_url_yyyy_mm_dd_slashes():
    """常见 /2024/11/08/ 格式（搜狐 / 新浪部分频道）"""
    from app.services.ai_service import extract_date_from_url
    d = extract_date_from_url("https://www.sohu.com/2024/11/08/news_12345.html")
    assert d is not None
    assert (d.year, d.month, d.day) == (2024, 11, 8)


def test_extract_date_from_url_dashed():
    """ISO-like dashes 格式 /news/2024-11-08/xxx"""
    from app.services.ai_service import extract_date_from_url
    d = extract_date_from_url("https://example.com/news/2024-11-08/article.html")
    assert d is not None
    assert (d.year, d.month, d.day) == (2024, 11, 8)


def test_extract_date_from_url_no_date():
    """URL 完全无日期路径"""
    from app.services.ai_service import extract_date_from_url
    assert extract_date_from_url("https://mp.weixin.qq.com/s/abcdefg") is None
    assert extract_date_from_url("") is None
    assert extract_date_from_url(None) is None  # type: ignore[arg-type]


# T003 [US1/US2/US3] published_at 优先级 ────────

def test_source_date_priority_url_wins():
    """URL 抽出 2024-11-08 vs citation.published_at = 2026-04-22 → 取 URL"""
    from app.services.ai_service import resolve_published_at

    result = resolve_published_at(
        url="https://sh.people.com.cn/n/2024/1108/c-x.html",
        citation_published_at="2026-04-22",
        snippet="该营地 2025-03-01 开放",
    )
    assert result is not None
    assert (result.year, result.month, result.day) == (2024, 11, 8)


def test_source_date_priority_citation_when_url_no_date():
    """URL 无日期 + citation.published_at = '2024-11-08' → 取 citation"""
    from app.services.ai_service import resolve_published_at

    result = resolve_published_at(
        url="https://mp.weixin.qq.com/s/abcd",
        citation_published_at="2024-11-08",
        snippet="发布于 2023-01-01",
    )
    assert result is not None
    assert (result.year, result.month, result.day) == (2024, 11, 8)


def test_source_date_priority_snippet_fallback():
    """URL 和 citation 都无 → fallback 到 snippet"""
    from app.services.ai_service import resolve_published_at

    result = resolve_published_at(
        url="https://mp.weixin.qq.com/s/abcd",
        citation_published_at=None,
        snippet="发布于 2025-03-10，该营地…",
    )
    assert result is not None
    assert (result.year, result.month, result.day) == (2025, 3, 10)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# spec 003-fix-fuzzy-marker：模糊位置点位不出 marker（Bug 1 修复）
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@pytest.mark.asyncio(loop_scope="session")
async def test_spot_dropped_when_geocode_none(monkeypatch):
    """spec 003 US1: geocode 完全失败 → spot 进 unmapped，不进 spots（不出 marker）"""
    from app.services import ai_service
    from unittest.mock import AsyncMock

    # mock geocode_with_amap 永远返回 None（模拟地址识别失败）
    monkeypatch.setattr(ai_service, "geocode_with_amap", AsyncMock(return_value=None))

    ai_result = {
        "spots": [{
            "name": "上海某营地",
            "address_hint": "上海",
            "source_ids": ["s001"],
        }],
        "unmapped": [],
    }
    sources = [{
        "id": "s001",
        "url": "https://example.com/article",
        "title": "上海露营地推荐",
        "snippet": "上海有很多营地",
        "domain": "example.com",
    }]

    spots, unmapped = await ai_service.normalize_candidates(ai_result, sources, "上海", 10)

    # 关键断言：spot 不在 spots（无 marker）
    assert all(s["name"] != "上海某营地" for s in spots), "geocode 失败的 spot 不应在 spots"
    # 但在 unmapped（仍可见文字）
    assert any(u["name"] == "上海某营地" for u in unmapped), "应该进 unmapped 文字展示"


@pytest.mark.asyncio(loop_scope="session")
async def test_spot_dropped_when_confidence_low(monkeypatch):
    """spec 003 US1: geocode 返回 confidence=low → 同样筛掉"""
    from app.services import ai_service
    from unittest.mock import AsyncMock

    monkeypatch.setattr(ai_service, "geocode_with_amap", AsyncMock(return_value={
        "lat": 31.2304,
        "lon": 121.4737,
        "confidence": "low",  # 低精度
        "provider": "amap:市",
        "matched_address": "上海市",
    }))

    ai_result = {
        "spots": [{"name": "模糊点", "address_hint": "上海某地", "source_ids": ["s001"]}],
        "unmapped": [],
    }
    sources = [{"id": "s001", "url": "https://example.com/a", "title": "t",
                "snippet": "s", "domain": "example.com"}]

    spots, unmapped = await ai_service.normalize_candidates(ai_result, sources, "上海", 10)
    assert all(s["name"] != "模糊点" for s in spots), "confidence=low 也应筛掉"
    assert any(u["name"] == "模糊点" for u in unmapped)


@pytest.mark.asyncio(loop_scope="session")
async def test_spot_kept_when_confidence_high(monkeypatch):
    """spec 003 US1 (正常路径): confidence=high → 正常进 spots（不要回归正常路径）"""
    from app.services import ai_service
    from unittest.mock import AsyncMock

    monkeypatch.setattr(ai_service, "geocode_with_amap", AsyncMock(return_value={
        "lat": 31.1234,
        "lon": 121.4567,
        "confidence": "high",
        "provider": "amap:兴趣点",
        "matched_address": "上海市闵行区浦江镇 XX 公园",
    }))

    ai_result = {
        "spots": [{"name": "精确点位", "address_hint": "上海市闵行区浦江镇XX路1号",
                   "source_ids": ["s001"]}],
        "unmapped": [],
    }
    sources = [{"id": "s001", "url": "https://example.com/a", "title": "t",
                "snippet": "s", "domain": "example.com"}]

    spots, unmapped = await ai_service.normalize_candidates(ai_result, sources, "上海", 10)
    assert any(s["name"] == "精确点位" for s in spots), "精确坐标应该正常出现在 spots"
    assert all(u["name"] != "精确点位" for u in unmapped)


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# spec 005-precise-geocoding: AI 抽精确地址 + geocoding city hint
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# T001 _is_precise_address 单元测试 ─────────────────────

def test_is_precise_address_street_level():
    """含街道/路/号 → True"""
    from app.services.ai_service import _is_precise_address
    assert _is_precise_address("上海市闵行区浦江镇红光路 1101 号") is True
    assert _is_precise_address("吕巷镇红光路 1101 号") is True
    assert _is_precise_address("浦江镇某村") is True  # 镇 + 村
    assert _is_precise_address("莫干山景区里的玖月营地") is True  # 景区 + 营地名
    assert _is_precise_address("黄浦江畔某点") is True  # 含具体场所


def test_is_precise_address_city_only():
    """只到城市/省份级 → False（应该筛掉）"""
    from app.services.ai_service import _is_precise_address
    assert _is_precise_address("上海") is False
    assert _is_precise_address("上海市") is False
    assert _is_precise_address("杭州") is False
    assert _is_precise_address("市中心") is False
    assert _is_precise_address("市区某处") is False
    assert _is_precise_address("浙江省") is False


def test_is_precise_address_empty():
    """空 / None → False"""
    from app.services.ai_service import _is_precise_address
    assert _is_precise_address("") is False
    assert _is_precise_address(None) is False  # type: ignore[arg-type]
    assert _is_precise_address("unknown") is False


def test_is_precise_address_district_only_borderline():
    """边界：只有区县 → 仍算精确（区县级 geocode 大致够用）"""
    from app.services.ai_service import _is_precise_address
    # 用户决策：宽松判断，含「区」就算 —— 否则会把"奉贤区"这种合理地址也筛掉
    assert _is_precise_address("奉贤区") is True
    assert _is_precise_address("青浦区朱家角镇") is True


def test_is_precise_address_country_or_region():
    """国家/大区 → False"""
    from app.services.ai_service import _is_precise_address
    assert _is_precise_address("中国") is False
    assert _is_precise_address("华东地区") is False


# T003 normalize_candidates 把 city-only 的 spot 进 unmapped ──────

@pytest.mark.asyncio(loop_scope="session")
async def test_normalize_candidates_drops_city_only_spot(monkeypatch):
    """spec 005 US1: address_hint 只到城市级 → 进 unmapped 不进 spots"""
    from app.services import ai_service
    from unittest.mock import AsyncMock

    # mock geocode_with_amap 永远返回 high confidence（确保不是 geocode 拦的）
    monkeypatch.setattr(ai_service, "geocode_with_amap", AsyncMock(return_value={
        "lat": 31.23, "lon": 121.47, "confidence": "high",
        "provider": "amap:兴趣点", "matched_address": "上海",
    }))

    ai_result = {
        "spots": [
            {"name": "上海某营地", "address_hint": "上海", "source_ids": ["s001"]},  # 城市级 → 应进 unmapped
            {"name": "精确营地", "address_hint": "闵行区浦江镇 XX 路 1 号", "source_ids": ["s002"]},  # 精确 → 进 spots
        ],
        "unmapped": [],
    }
    sources = [
        {"id": "s001", "url": "https://example.com/a", "title": "t1", "snippet": "s", "domain": "example.com"},
        {"id": "s002", "url": "https://example.com/b", "title": "t2", "snippet": "s", "domain": "example.com"},
    ]

    spots, unmapped = await ai_service.normalize_candidates(ai_result, sources, "上海", 10)

    # 关键断言：城市级 spot 进 unmapped，精确 spot 进 spots
    assert all(s["name"] != "上海某营地" for s in spots), "城市级 address_hint 不应进 spots"
    assert any(u["name"] == "上海某营地" for u in unmapped), "城市级 address_hint 应进 unmapped"
    assert any(s["name"] == "精确营地" for s in spots), "精确地址应进 spots"


# T005 geocode_query 接受 city/province hint ─────────────

@pytest.mark.asyncio
async def test_geocode_query_with_city_hint(httpx_mock: HTTPXMock):
    """spec 005 US2: geocode_query 接 city 参数，传给高德减少歧义"""
    import re
    from unittest.mock import patch, AsyncMock
    from app.services.amap_service import geocode_query

    # mock httpx 返回浙江莫干山坐标（GCJ-02）
    httpx_mock.add_response(
        url=re.compile(r"https://restapi\.amap\.com/v3/geocode/geo.*"),
        json={
            "status": "1",
            "geocodes": [{
                "location": "119.901,30.624",  # 浙江德清莫干山 GCJ-02
                "formatted_address": "浙江省湖州市德清县莫干山",
                "level": "景区",
            }],
        },
    )

    with patch("app.services.amap_service.cache_get", AsyncMock(return_value=None)), \
         patch("app.services.amap_service.cache_set", AsyncMock(return_value=None)), \
         patch("app.services.amap_service.amap_key", return_value="fake_key_for_test"):
        result = await geocode_query("莫干山", province="浙江省")

    assert result is not None
    lat, lon, name = result
    # WGS-84 转换后应在浙江莫干山附近（30.6, 119.9）
    assert 30.5 < lat < 30.8
    assert 119.8 < lon < 120.0
    # 验证 city/province 参数确实传给了高德
    request = httpx_mock.get_requests()[-1]
    url_str = str(request.url)
    assert "%E6%B5%99%E6%B1%9F%E7%9C%81" in url_str or "浙江省" in url_str, (
        f"province 应传给高德，实际 URL: {url_str[:200]}"
    )
