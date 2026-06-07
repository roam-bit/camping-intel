"""HTTP 级别集成测试：直接打 FastAPI app，验现有 dev Postgres 数据上的 API 行为。"""
from __future__ import annotations

import pytest

# session loop scope，与 client fixture 对齐，避免 SQLAlchemy async engine 跨 loop 报错
pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_health(client):
    r = await client.get("/api/v1/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"


async def test_list_places_returns_well_formed(client):
    """places 列表返回非空 + 关键字段齐全（places/total/search_metadata 三个顶层键）"""
    r = await client.get(
        "/api/v1/places",
        params={"lat": 30.2741, "lon": 120.1551, "radius_km": 80, "limit": 10},
    )
    assert r.status_code == 200
    d = r.json()
    assert {"total", "places", "search_metadata"}.issubset(d.keys())
    assert isinstance(d["places"], list)
    if d["places"]:
        place = d["places"][0]
        # 关键 schema 字段必有
        for field in ("id", "name", "type", "latitude", "longitude", "credibility_score", "status"):
            assert field in place, f"place 缺字段 {field}"


async def test_list_places_sort_credibility_desc_distance_asc(client):
    """同 credibility 内距离应单调非递减（P1-4 ST_DWithin + 排序验证）"""
    r = await client.get(
        "/api/v1/places",
        params={"lat": 30.2741, "lon": 120.1551, "radius_km": 50, "limit": 50},
    )
    assert r.status_code == 200
    items = r.json()["places"]
    prev_cred, prev_dist = 999, -1.0
    for p in items:
        cred = p["credibility_score"]
        dist = p.get("distance_km") or 0
        assert cred <= prev_cred, f"credibility 应单调非递增: {prev_cred} -> {cred}"
        if cred == prev_cred:
            assert dist >= prev_dist - 0.01, f"同 cred 内距离倒序: {prev_dist} -> {dist}"
        prev_cred, prev_dist = cred, dist


async def test_list_places_radius_filter(client):
    """ST_DWithin 应该过滤掉超出 radius_km 的点"""
    radius = 10  # 10km 内才返回
    r = await client.get(
        "/api/v1/places",
        params={"lat": 30.2741, "lon": 120.1551, "radius_km": radius, "limit": 100},
    )
    assert r.status_code == 200
    items = r.json()["places"]
    for p in items:
        d = p.get("distance_km")
        if d is not None:
            # 留 0.1km 容差（PostGIS Geography 距离计算和应用层 haversine 可能微差）
            assert d <= radius + 0.1, f"返回 {p['name']} 距离 {d}km 超出 radius={radius}km"


async def test_place_detail_404_for_unknown(client):
    """detail 接口对不存在 uuid 返回 404"""
    fake_uuid = "00000000-0000-0000-0000-000000000000"
    r = await client.get(f"/api/v1/places/{fake_uuid}")
    assert r.status_code == 404


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# spec 001-fix-source-geo-filter：来源点位与搜索词地理一致性修复
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

# ─────────────── T004 [US1] 本地 detect 命中（上海）───────────────

async def test_q_param_with_local_detect_shanghai(client):
    """US1 + SC-001: 搜"上海"时，所有返回点位的坐标必须在上海行政区内。

    设计要点：
    - 测试对 DB 状态宽容（places 可空）—— 关键断言是「不出现非上海坐标」
    - search_metadata 必须包含 detected_place / search_center / geocoder
    - geocoder 必须是 "local"（命中本地 14 城市字典）
    """
    r = await client.get(
        "/api/v1/places",
        params={"lat": 30.27, "lon": 120.15, "q": "上海露营地", "limit": 50},
    )
    assert r.status_code == 200
    d = r.json()

    # 断言 1: metadata 字段必有
    meta = d["search_metadata"]
    assert meta.get("detected_place") == "上海"
    assert meta.get("geocoder") == "local"
    sc = meta.get("search_center")
    assert sc is not None
    assert abs(sc["lat"] - 31.2304) < 0.01
    assert abs(sc["lon"] - 121.4737) < 0.01

    # 断言 2: 所有点位都在上海行政区（lat 30.7-31.9, lon 120.9-122.1）
    for p in d["places"]:
        assert 30.7 < p["latitude"] < 31.9, f"点位 lat 越界: {p['name']} @ {p['latitude']}"
        assert 120.9 < p["longitude"] < 122.1, f"点位 lon 越界: {p['name']} @ {p['longitude']}"


# ─────────────── T008 [US2] 高德 fallback（漠河）───────────────

async def test_q_unknown_city_amap_fallback(client):
    """US2 + SC-003: detect 未命中（漠河不在 14 城市表）→ geocode_query 兜底 → geocoder='amap'

    用 mock 替换 geocode_query，避免依赖真实高德 API。
    """
    from unittest.mock import patch, AsyncMock

    mock_geo = AsyncMock(return_value=(53.471795, 122.539736, "黑龙江省漠河市"))
    with patch("app.routers.places.geocode_query", mock_geo):
        r = await client.get(
            "/api/v1/places",
            params={"lat": 30.27, "lon": 120.15, "q": "漠河露营", "limit": 50},
        )

    assert r.status_code == 200
    d = r.json()
    meta = d["search_metadata"]
    assert meta["geocoder"] == "amap"
    assert "漠河" in (meta.get("detected_place") or "")
    sc = meta["search_center"]
    assert abs(sc["lat"] - 53.47) < 0.01
    assert abs(sc["lon"] - 122.54) < 0.01

    # DB 里没漠河附近数据，places 应为空（或个别在 80km 内的）
    for p in d["places"]:
        assert abs(p["latitude"] - 53.47) < 0.8, f"非漠河点位混入: {p['name']} @ {p['latitude']}"
        assert abs(p["longitude"] - 122.54) < 1.4, f"非漠河点位混入: {p['name']}"

    # 验证 fallback 路径被触发（spec 005 后签名加 province kwarg，宽松检查）
    mock_geo.assert_awaited_once()
    assert "漠河露营" in str(mock_geo.await_args)


# ─────────────── T010 [US3] 无地理意图回归防护 ───────────────

async def test_q_no_geo_intent_keeps_user_location(client):
    """US3 + SC-004: 搜"露营"（detect + geocode 都失败）→ 用 lat/lon 作为中心，geocoder=None"""
    from unittest.mock import patch, AsyncMock

    # mock geocode_query 也返回 None（模拟"露营"在高德也识别不出地理位置）
    mock_geo = AsyncMock(return_value=None)
    with patch("app.routers.places.geocode_query", mock_geo):
        r = await client.get(
            "/api/v1/places",
            params={"lat": 30.27, "lon": 120.15, "q": "露营", "limit": 50},
        )

    assert r.status_code == 200
    d = r.json()
    meta = d["search_metadata"]
    # 关键契约：geocoder=None + search_center=None（保持原行为）
    assert meta["geocoder"] is None
    assert meta["detected_place"] is None
    assert meta["search_center"] is None
    # search_metadata.lat/lon 应等于传入的 lat/lon（向后兼容字段）
    assert meta["lat"] == 30.27
    assert meta["lon"] == 120.15

    # 所有返回点位应该在杭州 80km 内（向后兼容行为）
    for p in d["places"]:
        # 杭州 30.27,120.15 ± 0.8° 大约就是 80km 内
        assert abs(p["latitude"] - 30.27) < 1.0, f"超出杭州 80km: {p['name']}"


# ─────────────── 不带 q 参数（旧调用方）行为不变 ───────────────

async def test_q_omitted_backward_compatible(client):
    """旧调用方不传 q → search_metadata 里 geocoder=None，行为完全不变。"""
    r = await client.get(
        "/api/v1/places",
        params={"lat": 30.27, "lon": 120.15, "limit": 10},
    )
    assert r.status_code == 200
    meta = r.json()["search_metadata"]
    assert meta["geocoder"] is None
    assert meta["detected_place"] is None


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# spec 004-filter-fuzzy-places：过滤 low confidence 历史脏数据
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

async def test_places_filter_excludes_low_confidence(client):
    """spec 004 US1: places API 必须过滤 location_confidence=low 的 Place

    DB 里有 405 条 low + 65 条 medium 在杭州 80km 内（截至 2026-05-18）。
    过滤后应该 ≤ 65 个（不含 low）。
    """
    r = await client.get(
        "/api/v1/places",
        params={"lat": 30.27, "lon": 120.15, "radius_km": 80, "limit": 200},
    )
    assert r.status_code == 200
    d = r.json()

    # 关键断言：返回的所有 Place 的 confidence 不应是 low / pending / NULL
    for p in d["places"]:
        conf = p.get("location_confidence")
        assert conf in ("high", "medium"), (
            f"❌ {p['name']} 的 confidence={conf!r}，应该被过滤"
        )

    # total 数量应该明显减少（杭州 80km 之前 470 个 → 现在 ≤ 65）
    assert d["total"] <= 65, f"过滤后应 ≤65 个，实际 {d['total']}"
