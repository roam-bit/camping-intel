# Implementation Plan: 来源点位与搜索词地理一致性修复

**Branch**: `fix/bug-2-source-filter` | **Date**: 2026-05-18 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/001-fix-source-geo-filter/spec.md`

---

## Summary

把 `/api/v1/places` 接口改成"按搜索词的地理意图过滤"。改动核心 3 块：
1. **后端 places router** 加 `q` 参数 + 3 段式 search_center 决策（本地 dict → 高德 geocoding → 用户位置 fallback）
2. **新增 `geocode_query` 服务**（封装高德 API + Redis 缓存）
3. **前端 places API client** 调用时透传 query 字符串 + 处理新的空状态响应

预计代码改动：**3 个文件 + 1 个新文件**，约 150 行。

---

## Technical Context

| 项 | 值 |
|---|---|
| **Language/Version** | Python 3.9 (backend) / TypeScript + React 18 (frontend) |
| **Primary Dependencies** | FastAPI / SQLAlchemy async / PostGIS / Redis / Taro 4 / httpx |
| **Storage** | PostgreSQL + PostGIS (places 表) / Redis (cache layer) |
| **Testing** | pytest (后端 21 用例已有) / tsc (前端类型) |
| **Target Platform** | macOS dev → 未来 weapp + 手机端 APP |
| **Project Type** | Web application (frontend + backend) |
| **Performance Goals** | places API P95 < 300ms (含高德 geocoding fallback)，cache hit < 50ms |
| **Constraints** | 高德 geocoding 必须有 2s 超时静默失败；不阻塞主流程 |
| **Scale/Scope** | 单机部署期；日 query < 100 次（演示阶段）|

## Constitution Check

⚠️ 项目 `.specify/memory/constitution.md` 还是 Spec Kit 初始化的模板（未填）。
本次跳过 Constitution Check，参照 `CLAUDE.md` 的「开发工作流（4 件套防回归）」作为隐式 constitution：
- 新功能必加 happy-path 测试 ✅（本 plan 包含）
- 修 bug 必加 regression 测试 ✅（4 条 regression test 计划）
- pre-commit hook 自动守门 ✅（已就位）

**后续 backlog**：抽时间用 `/speckit-constitution` 正式立项目原则。

---

## Architecture

### 涉及文件清单

```
backend/
├── app/
│   ├── routers/
│   │   └── places.py                    # 改：加 q 参数 + search_center 3 段式决策
│   └── services/
│       ├── amap_service.py              # 改：新增 geocode_query() 函数
│       └── cache.py                     # （已有，复用 Redis 接口）
└── tests/
    └── test_places_api.py               # 改：新增 4 条 regression test

frontend/
├── src/
│   ├── api/
│   │   └── client.ts                    # 改：listPlaces() 加 q 参数
│   └── pages/
│       └── index/
│           └── index.tsx                # 改：调 listPlaces 透传 query + 空状态文案
```

### 数据流（修复后）

```
用户搜「上海露营地」
       │
       ▼
前端 index.tsx 触发 SSE 流（不变）
       │
       ├─► 并行：调 listPlaces(lat, lon, radius_km, q="上海露营地")
       │       │
       │       ▼
       │   后端 places.py 收到 q
       │       │
       │       ▼
       │   1. detect_place_center("上海露营地") → ("上海", 31.23, 121.47) ✅
       │      │ (本地命中，跳过高德)
       │      ▼
       │   2. search_center = (31.23, 121.47)
       │      │
       │      ▼
       │   3. PostGIS ST_DWithin(geom, search_center, 80km)
       │      │
       │      ▼
       │   返回 11 个上海点位（或空数组）+ metadata{detected_place, search_center, geocoder}
       │
       └─► 前端拿到 places 响应：
           ├─ 有数据 → 渲染卡片列表
           └─ 空数组 + search_center != null → 显示"该地区暂无点位..."文案
```

### 高德 geocoding fallback 路径（搜「漠河」）

```
detect_place_center("漠河") → None（不在 14 城市表）
       │
       ▼
检查 Redis cache: geocode:{md5("漠河")} → miss
       │
       ▼
调高德 /v3/geocode/geo?address=漠河&key=AMAP_WEB_KEY（2s 超时）
       │
       ├─ 成功 → 返回 (lat, lon)，写入 Redis (TTL 7 天) → 用作 search_center
       └─ 失败/超时 → 返回 None → fallback 到用户位置（行为同搜"露营"）
```

---

## Implementation Approach

按 FR 分组实施，**测试驱动**（每改一块代码前先写 test，hook 守门）：

### Phase 1: 后端 geocode_query 服务（FR-006/007/008）

**文件**：`backend/app/services/amap_service.py`

**新增函数**：
```python
async def geocode_query(q: str) -> tuple[float, float, str] | None:
    """高德 geocoding fallback。带 Redis 缓存 + 2s 超时静默失败。"""
    cache_key = f"geocode:{hashlib.md5(q.encode()).hexdigest()}"
    cached = await cache_get(cache_key)
    if cached:
        return cached  # 已经是 tuple

    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            resp = await client.get(
                "https://restapi.amap.com/v3/geocode/geo",
                params={"address": q, "key": settings.amap_web_key}
            )
        data = resp.json()
        if data.get("status") == "1" and data.get("geocodes"):
            loc = data["geocodes"][0]["location"]  # "lon,lat" 格式
            lon, lat = map(float, loc.split(","))
            name = data["geocodes"][0].get("formatted_address", q)
            result = (lat, lon, name)
            await cache_set(cache_key, result, ttl=7 * 86400)
            return result
    except (httpx.TimeoutException, httpx.HTTPError, ValueError, KeyError):
        pass
    return None
```

**新依赖**：无（httpx / hashlib / cache 都已有）

### Phase 2: 后端 places router 改造（FR-001/002/003/004/005）

**文件**：`backend/app/routers/places.py`

**API 签名变化**：
```python
@router.get("")
async def list_places(
    lat: float, lon: float, radius_km: int = 80,
    category: str = "全部", min_credibility: float = 0, limit: int = 240,
    q: str | None = Query(None, description="搜索词，用于识别地理意图"),
    db: AsyncSession = Depends(get_db)
) -> dict:
```

**search_center 3 段式决策**：
```python
search_center_lat, search_center_lon = lat, lon  # 默认用户位置
detected_place = None
geocoder = None

if q:
    detected = detect_place_center(q, _tokenize(q))
    if detected:
        search_center_lat, search_center_lon, detected_place = detected
        geocoder = "local"
    else:
        geo_result = await geocode_query(q)
        if geo_result:
            search_center_lat, search_center_lon, detected_place = geo_result
            geocoder = "amap"
        # else: 保持 lat/lon 默认值，geocoder = None

# 用 search_center 做 PostGIS ST_DWithin 过滤
# 返回 metadata: {detected_place, search_center: {lat, lon}, geocoder}
```

**cache key 改动（FR-012）**：
```python
cache_key_parts = [
    f"places:{round(search_center_lat, 2)}:{round(search_center_lon, 2)}",
    f":r{radius_km}:c{category}:m{min_credibility}:l{limit}",
]
```

### Phase 3: 前端 client + UI 改造（FR-009/010/011）

**文件 1**：`frontend/src/api/client.ts`

```typescript
export interface PlacesResponse {
  places: Place[]
  metadata?: {
    detected_place: string | null
    search_center: { lat: number; lon: number } | null
    geocoder: "local" | "amap" | null
  }
}

export async function listPlaces(
  lat: number, lon: number, radiusKm = 80,
  options: { q?: string; category?: string; limit?: number } = {}
): Promise<PlacesResponse> {
  // 加 q 参数到 query string
}
```

**文件 2**：`frontend/src/pages/index/index.tsx`

- 调 `listPlaces` 时传 `q: query`（当前搜索词）
- 收到响应后：
  - 如果 `places.length === 0 && metadata?.search_center !== null` → 显示空状态文案
  - 否则正常渲染卡片列表

### Phase 4: 测试 + 验证（SC-005）

**4 条 regression test**（`backend/tests/test_places_api.py`）：

```python
async def test_geo_filter_local_detect(client):
    """User Story 1: 搜"上海"返回的点都在上海"""
    r = await client.get("/api/v1/places?lat=30.27&lon=120.15&q=上海露营地")
    for p in r.json()["places"]:
        assert 30.7 < p["latitude"] < 31.9
        assert 120.9 < p["longitude"] < 122.1
    assert r.json()["metadata"]["geocoder"] == "local"

async def test_geo_filter_amap_fallback(client, httpx_mock):
    """User Story 2 + geocoding fallback: 搜"漠河"通过高德 mock 返回坐标"""
    httpx_mock.add_response(json={"status": "1", "geocodes": [{"location": "122.5388,53.4717", ...}]})
    r = await client.get("/api/v1/places?lat=30.27&lon=120.15&q=漠河露营")
    assert r.json()["metadata"]["geocoder"] == "amap"
    assert r.json()["places"] == []  # DB 里没漠河数据

async def test_no_geo_intent_fallback(client):
    """User Story 3: 搜"露营"无地理意图，返回用户位置周边"""
    r = await client.get("/api/v1/places?lat=30.27&lon=120.15&q=露营")
    assert r.json()["metadata"]["geocoder"] is None
    # 所有点都在杭州 80km 内

async def test_geocode_cache_hit(client, httpx_mock):
    """SC-007: 高德 cache 7 天，同 query 不重复调"""
    httpx_mock.add_response(...)  # 设 1 次
    await client.get("/api/v1/places?...q=漠河")  # 第 1 次（打 mock）
    await client.get("/api/v1/places?...q=漠河")  # 第 2 次（应该 cache hit）
    assert httpx_mock.get_requests_count() == 1
```

---

## Risks & Mitigations

| 风险 | 概率 | 影响 | 缓解措施 |
|---|---|---|---|
| 高德 API 429（quota 用尽）| 低 | 中 | Redis cache 7 天 + 监控调用频率 |
| 高德 API 慢（>2s）| 中 | 中 | 硬超时 2s，超时静默 fallback 到用户位置 |
| 旧 cache 与新 cache key 不兼容 | 高 | 低 | 不清理旧 cache，自然过期（最长 1h）；新 key 立刻生效 |
| 前端调 listPlaces 时 `q` 为空字符串 vs undefined 不一致 | 中 | 低 | 后端用 `if q and q.strip()` 严格判断 |
| 改 places API 签名影响其他调用方 | 低 | 中 | `q` 是 Optional，旧调用方零改动（保持向后兼容）|

---

## Rollback Plan

如果上线后发现严重问题：
1. **快速回滚**：`git revert <commit>` + 重启后端 + 浏览器刷新
2. **配置开关**：保留 `q` 参数但内部 `if False:` 跳过新逻辑（无需 revert 代码）
3. **数据无影响**：本次不动 DB schema，不动数据

---

## 后续不在本次范围

- 清洗 DB 里的"烟台/牟平/福山"等冷启动脏数据（spec assumption 已说明）
- 14 城市表外的省份级支持（如"新疆"用更大半径）
- 用户拖图后搜纯品类 query 的 UX 微调

---

## Constitution Re-check（Post-design）

✅ 单文件改动 < 200 行（每个文件改动可控）
✅ 测试先行（FR + SC → test → implementation）
✅ 不引入新依赖（httpx / cache 都已有）
✅ 不破坏现有 API 调用方（`q` Optional 向后兼容）

可以进入 `/speckit-tasks` 阶段。
