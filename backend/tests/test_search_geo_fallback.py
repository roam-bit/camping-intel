"""spec-017: 搜索地理意图三段式 resolver 测试。

覆盖 5 个 case（contracts/search-api.md）：
- US1 T007: 字典命中 → 不调 amap
- US1 T008: 字典 miss + amap 命中
- US2 T013: 字典 + amap 都失败 → unrecognized_location
- US2 T014: amap 超时 → unrecognized_location
- US2 T015: 第 2 次重复失败 query → 命中 negative cache、amap 未被调用
- US3 T021: query 全是 generic token → 不调 amap、不报错
"""
from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, patch

# session loop scope 与 client fixture 对齐
pytestmark = pytest.mark.asyncio(loop_scope="session")


# ─────────────── 工具：发起一次 search 请求 ───────────────

async def _post_search(client, q: str, **kwargs):
    """POST /api/v1/search，返回 (status_code, json_body)。"""
    body = {
        "q": q,
        "limit": kwargs.get("limit", 12),
        "radius_km": kwargs.get("radius_km", 80),
        "lat": kwargs.get("lat", 30.2741),
        "lon": kwargs.get("lon", 120.1551),
    }
    r = await client.post("/api/v1/search", json=body)
    return r.status_code, r.json()


# ─────────────── US1: 字典命中、不调 amap ───────────────

async def test_dict_hit_no_amap_call(client):
    """T007: query=「南昌露营地」字典已有「南昌」，amap 不该被调用。"""
    mock_geo = AsyncMock(return_value=(99.0, 99.0, "FAKE_AMAP_RESULT"))  # 故意给离谱值，命中说明调了
    with patch("app.routers.search.geocode_query", mock_geo):
        status, data = await _post_search(client, "南昌露营地")

    assert status == 200
    sb = data["source_breakdown"]
    assert sb["search_center_source"] == "dict", f"应走字典快路径，实际 {sb.get('search_center_source')}"
    # 南昌坐标 ≈ (28.68, 115.86)；用宽松断言、字典具体值可能微调
    assert abs(sb["search_center"]["lat"] - 28.68) < 0.5, f"search_center lat 不在南昌附近: {sb['search_center']}"
    assert abs(sb["search_center"]["lon"] - 115.86) < 0.5
    # amap 不应被调用（字典已命中）
    mock_geo.assert_not_called()


# ─────────────── US1: 字典 miss + amap 命中 ───────────────

async def test_amap_fallback_hit(client):
    """T008: 字典里没的地名「景德镇露营地」，mock amap 返回景德镇坐标。"""
    mock_geo = AsyncMock(return_value=(29.27, 117.18, "江西省景德镇市"))
    with patch("app.routers.search.geocode_query", mock_geo):
        status, data = await _post_search(client, "景德镇露营地")

    assert status == 200
    sb = data["source_breakdown"]
    assert sb["search_center_source"] == "amap", f"应走 amap 兜底，实际 {sb.get('search_center_source')}"
    assert sb["detected_place"] == "江西省景德镇市"
    assert abs(sb["search_center"]["lat"] - 29.27) < 0.01
    assert abs(sb["search_center"]["lon"] - 117.18) < 0.01
    mock_geo.assert_called_once()


# ─────────────── US2: amap 也失败 → unrecognized_location ───────────────

async def test_amap_fallback_miss_returns_unrecognized(client):
    """T013: 字典 + amap 都识别不到 → warning_code='unrecognized_location'、不调 AI/DB。"""
    mock_geo = AsyncMock(return_value=None)  # amap 返回 None = 识别失败
    with patch("app.routers.search.geocode_query", mock_geo):
        # 用不太可能撞 negative cache 的 query
        status, data = await _post_search(client, "spec017测试不存在地名XYZ营地")

    assert status == 200
    assert data["warning_code"] == "unrecognized_location"
    assert "无法识别" in data["warning"]
    assert "spec017测试不存在地名XYZ营地" in data["warning"]  # 引用用户输入
    # 关键不变量：spec FR-007/009/010
    assert data["spots"] == []
    assert data["unmapped_candidates"] == []
    assert data["source_breakdown"]["search_center"] is None
    assert data["source_breakdown"]["detected_place"] is None
    assert data["source_breakdown"]["search_center_source"] == "none"
    assert data["source_breakdown"]["strategy"] == "unrecognized_location"
    # 不调 AI、不查 DB
    assert data["provider"]["llm"] == "none"
    assert data["extract_pending"] is False
    assert data["extract_cache_key"] is None


# ─────────────── US2: amap 抛异常 → 也算 unrecognized ───────────────

async def test_amap_exception_treated_as_unrecognized(client):
    """T014: amap 抛网络异常（模拟 timeout），等同识别失败。"""
    import httpx
    mock_geo = AsyncMock(side_effect=httpx.TimeoutException("amap timeout"))
    with patch("app.routers.search.geocode_query", mock_geo):
        status, data = await _post_search(client, "spec017异常测试XYZ营地")

    assert status == 200
    assert data["warning_code"] == "unrecognized_location"
    assert data["source_breakdown"]["search_center"] is None


# ─────────────── US2: negative cache 命中、第 2 次不调 amap ───────────────

async def test_negative_cache_skips_amap_on_repeat(client):
    """T015: 失败 query 第 2 次重试应命中 negative cache，amap 不该被调用第 2 次。"""
    from app.routers.search import _normalize_query, _amap_negative_cache_set
    # 主动写一条 negative cache，模拟「之前已识别失败」
    query = "spec017negcache已缓存的失败query营地"
    await _amap_negative_cache_set(_normalize_query(query))

    mock_geo = AsyncMock(return_value=(99.0, 99.0, "SHOULD_NOT_HIT"))  # 即使 mock 命中也不该被调用
    with patch("app.routers.search.geocode_query", mock_geo):
        status, data = await _post_search(client, query)

    assert status == 200
    assert data["warning_code"] == "unrecognized_location"
    assert data["source_breakdown"]["search_center"] is None
    # 关键：amap 未被调用（命中 negative cache 短路）
    mock_geo.assert_not_called()


# ─────────────── US3: query 全是 generic word → 不调 amap、用 fallback ───────────────

async def test_province_level_refined_by_amap(client):
    """spec-017 hardening: detect_place_center 走 _infer_province_from_text 返回省级名时
    （如「盐城露营地」→「江苏省」→ 南京坐标 32.06,118.79），应让 amap 精化拿到城市级坐标。

    确保用户搜「盐城」时不会被误导到 250km 外的南京。
    """
    # mock amap 返回盐城的真实坐标（包含「盐城」token）
    mock_geo = AsyncMock(return_value=(33.35, 120.16, "江苏省盐城市"))
    with patch("app.routers.search.geocode_query", mock_geo):
        status, data = await _post_search(client, "盐城露营地")

    assert status == 200
    sb = data["source_breakdown"]
    # 关键断言：应走 amap 精化、不是 dict 返回省级南京坐标
    assert sb["search_center_source"] == "amap", f"应走 amap 精化、实际 {sb.get('search_center_source')}"
    assert "盐城" in sb["detected_place"], f"detected 应含盐城、实际 {sb['detected_place']}"
    # 坐标应在盐城附近（33.35, 120.16）、不是南京（32.06, 118.79）
    assert abs(sb["search_center"]["lat"] - 33.35) < 0.5, f"应在盐城附近、实际 {sb['search_center']}"
    assert abs(sb["search_center"]["lon"] - 120.16) < 0.5
    mock_geo.assert_called_once()


async def test_no_place_token_keeps_user_location_no_amap(client):
    """T021: query=「附近露营点」全是 generic_token（附近/露营），应用用户 lat/lon、不调 amap、无 warning。

    注：「免费露营地」会被 jieba 分为 ['免费', '露营地']，而「露营地」合成词不在
    _GENERIC_DOMAIN_TOKENS 里（只收了「露营」「营地」分开词）→ 被当 place_token、误触 amap。
    这里用「附近露营点」实际分词为 ['附近', '露营']、两个都是 generic，是干净的 no_place_token 测试 case。
    """
    mock_geo = AsyncMock(return_value=(99.0, 99.0, "SHOULD_NOT_HIT"))
    with patch("app.routers.search.geocode_query", mock_geo):
        status, data = await _post_search(client, "附近露营点", lat=30.2741, lon=120.1551)

    assert status == 200
    # 不该触发 unrecognized
    assert data["warning_code"] != "unrecognized_location"
    sb = data["source_breakdown"]
    assert sb["search_center_source"] == "no_place_token", f"应是 no_place_token，实际 {sb.get('search_center_source')}"
    # 用户位置传过去
    assert abs(sb["search_center"]["lat"] - 30.2741) < 0.01
    assert abs(sb["search_center"]["lon"] - 120.1551) < 0.01
    # amap 不该被调用
    mock_geo.assert_not_called()


# ─────────────── 回归：莫干山必须走字典，不准掉进 amap 同名陷阱 ───────────────

async def test_moganshan_dict_hit_regression(client):
    """回归（2026-06-12）：「莫干山」曾不在字典里 → 走 amap 兜底 → amap 返回
    福建泉州安溪县的同名小地名 → 搜索中心跑偏 500km+、DB 0 命中、AI 白等 30s+。
    首页示例芯片「莫干山附近营地」一点就翻车。防止这个 bug 再来：
    莫干山必须字典命中（浙江德清坐标），amap 不被调用。"""
    mock_geo = AsyncMock(return_value=(25.06, 118.19, "福建省泉州市安溪县莫干山"))  # 复现当时的错误返回
    with patch("app.routers.search.geocode_query", mock_geo):
        status, data = await _post_search(client, "莫干山附近营地")

    assert status == 200
    sb = data["source_breakdown"]
    assert sb["search_center_source"] == "dict", f"莫干山应走字典，实际 {sb.get('search_center_source')}"
    # 莫干山在浙江德清（≈30.585, 119.877），绝不能在福建（lat≈25）
    assert abs(sb["search_center"]["lat"] - 30.585) < 0.5, f"search_center 跑偏: {sb['search_center']}"
    assert abs(sb["search_center"]["lon"] - 119.877) < 0.5
    mock_geo.assert_not_called()


# ─────────────── 开发者面板：prompt 只读预览接口 ───────────────

async def test_dev_prompt_preview(client):
    """开发者抽屉的 prompt 预览：limit 旋钮要真实反映到提示词文本里，且 50 封顶。"""
    r = await client.get("/api/v1/dev/prompt-preview", params={"q": "莫干山附近营地", "limit": 24})
    assert r.status_code == 200
    data = r.json()
    assert "最多列出 24 个候选" in data["prompt"]
    assert "莫干山附近营地" in data["prompt"]
    assert data["limit_effective"] == 24

    r2 = await client.get("/api/v1/dev/prompt-preview", params={"limit": 999})
    assert r2.json()["limit_effective"] == 50
    assert "最多列出 50 个候选" in r2.json()["prompt"]
