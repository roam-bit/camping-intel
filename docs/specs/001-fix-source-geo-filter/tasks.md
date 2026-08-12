---
description: "Task list for 001-fix-source-geo-filter"
---

# Tasks: 来源点位与搜索词地理一致性修复

**Input**: Design from `specs/001-fix-source-geo-filter/`

**Prerequisites**: spec.md ✅, plan.md ✅

**Tests**: ✅ **Required**（4 件套规则 3：修 bug 必加 regression test）

**Organization**: Tasks grouped by User Story for independent implementation/test/delivery.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: 可与同 phase 内其他 [P] 任务并行执行（改不同文件，无依赖）
- **[Story]**: US1 / US2 / US3，对应 spec.md 的 User Story
- 严格 TDD：测试任务在实现任务之前

---

## Phase 1: Setup（共享基础）

- [ ] **T001** 验证当前 worktree 状态 + 依赖就位
  - 当前在 `fix/bug-2-source-filter` 分支 ✅（已切好）
  - 检查 venv 里 `httpx` 已装（amap_service 已经在用）
  - `cd backend && /Users/yihan_guo/Desktop/旅居产品_副本/.venv/bin/python -c "import httpx; print(httpx.__version__)"`
  - **产出**：confirm 一句话，无代码改动

---

## Phase 2: Foundation —— `geocode_query` 服务（FR-006/007/008）

**目标**：先建好"高德 geocoding fallback"基础服务，US1/US2 都依赖它。

- [ ] **T002** [US2] 写 `geocode_query` 单元测试（TDD 先行）
  - 文件：`backend/tests/test_amap_service.py`（新建）
  - 测试用例：
    - `test_geocode_query_success`：mock httpx 返回成功，断言返回 (lat, lon, name) tuple
    - `test_geocode_query_timeout`：mock httpx raise TimeoutException，断言返回 None
    - `test_geocode_query_amap_status_zero`：mock 高德返回 status=0，断言返回 None
    - `test_geocode_query_cache_hit`：第二次调同 query 不打 httpx
  - **跑**：`pytest backend/tests/test_amap_service.py` → 应该 **全部失败**（函数还没实现）

- [ ] **T003** [US2] 实现 `geocode_query` 函数
  - 文件：`backend/app/services/amap_service.py`
  - 实现 plan.md 里 Phase 1 的代码
  - 用现有 `httpx.AsyncClient` + 现有 `cache_get/cache_set`（from `app.services.cache`）
  - **跑**：`pytest backend/tests/test_amap_service.py` → **4 条全部 pass**

---

## Phase 3: places API 改造（FR-001/002/003/004/005/012）

**目标**：places API 接受 `q` 参数 + 按地理意图过滤。

### Phase 3.A：US1 主路径（local detect → 上海 case）

- [ ] **T004** [US1] 写 `test_geo_filter_local_detect` 测试
  - 文件：`backend/tests/test_places_api.py`（已存在，append）
  - 测试用例：`test_q_param_with_local_detect_shanghai`
    - GIVEN: DB 里有杭州 + 上海 mock 数据
    - WHEN: `GET /api/v1/places?lat=30.27&lon=120.15&q=上海露营地`
    - THEN: 所有返回点位 lat ∈ (30.7, 31.9), lon ∈ (120.9, 122.1)
    - AND: `response.metadata.geocoder == "local"`
    - AND: `response.metadata.detected_place == "上海"`
  - **跑**：失败（places.py 还没改）

- [ ] **T005** [US1] places.py 加 `q` 参数 + `detect_place_center` 集成
  - 文件：`backend/app/routers/places.py`
  - 改 `list_places` 函数签名加 `q: str | None = Query(None)`
  - 加 search_center 决策逻辑（先 local detect，未识别保持 lat/lon）
  - 暂时**不接 geocode_query**（下一步加）
  - **跑**：`pytest backend/tests/test_places_api.py::test_q_param_with_local_detect_shanghai` → pass

- [ ] **T006** [US1] places.py 响应加 metadata 区
  - 同一文件：返回值结构改为：
    ```python
    {"places": [...], "metadata": {"detected_place": ..., "search_center": ..., "geocoder": ...}}
    ```
  - 注意：**保持向后兼容** —— 旧调用方期望直接是 `[Place]`，所以检查现有 client.ts 看是直接消费还是有 wrap

- [ ] **T007** [US1] places.py 改 cache key 包含 search_center
  - 同一文件，cache_key 计算函数（如果有）加 `round(search_center_lat, 2)` + `round(search_center_lon, 2)`

### Phase 3.B：US2 geocoding fallback（漠河 case）

- [ ] **T008** [P][US2] 写 `test_geo_filter_amap_fallback` 测试
  - 文件：`backend/tests/test_places_api.py`（append）
  - 用 `pytest-httpx` mock 高德 API 返回（漠河坐标）
  - 测试 case：`test_q_unknown_city_amap_fallback`
    - WHEN: `q=漠河露营`（不在 14 城市表）
    - THEN: `metadata.geocoder == "amap"`，places 数组 = `[]`（DB 无漠河数据）

- [ ] **T009** [US2] places.py 集成 `geocode_query` fallback
  - 同 `backend/app/routers/places.py`
  - 在 `detect_place_center` 未识别时调 `await geocode_query(q)`
  - **跑**：T008 测试 pass

### Phase 3.C：US3 无地理意图回归防护

- [ ] **T010** [P][US3] 写 `test_no_geo_intent_fallback` 测试
  - 文件：`backend/tests/test_places_api.py`（append）
  - 测试 case：`test_q_no_geo_intent_keeps_user_location`
    - WHEN: `q=露营`（detect 和 geocode 都未识别）—— mock geocode_query 返回 None
    - THEN: 用 lat/lon 作为中心，所有返回点位在 80km 内
    - AND: `metadata.geocoder is None`

- [ ] **T011** [US3] 验证 T010 在当前实现下 pass（无需改 places.py）
  - 因为 T005 的 "未识别保持 lat/lon" 逻辑已经覆盖
  - 跑测试确认

### Phase 3.D：Cache 验证

- [ ] **T012** [P] 写 `test_geocode_cache_hit` 测试（SC-007）
  - 文件：`backend/tests/test_amap_service.py`（append）
  - 测试 case：同 query 调两次，httpx mock 只触发 1 次

---

## Phase 4: 前端改造（FR-009/010/011）

- [ ] **T013** [US1] `client.ts`：`listPlaces` 加 `q` 参数
  - 文件：`frontend/src/api/client.ts`
  - 函数签名扩展 `options.q?: string`，拼到 query string

- [ ] **T014** [US1] `client.ts`：`PlacesResponse` 类型加 `metadata` 字段
  - 同文件：`metadata?: {detected_place, search_center, geocoder}` 加进 type

- [ ] **T015** [US1] `index.tsx`：调 `listPlaces` 时传 `q`
  - 文件：`frontend/src/pages/index/index.tsx`
  - 在搜索 handler 里找到现有 `listPlaces(...)` 调用，加 `q: text`

- [ ] **T016** [US2] `index.tsx`：处理空状态
  - 同文件：渲染卡片列表前先判断
    - `if (places.length === 0 && metadata?.search_center) → 显示文案`
    - `else → 渲染列表`
  - 文案：「该地区暂无点位，AI 仍在为你联网搜索」

- [ ] **T017** [P][US1] 跑 `tsc --noEmit` 验证前端类型无错
  - `cd frontend && /opt/homebrew/bin/npx tsc --noEmit`

---

## Phase 5: 集成验证 + commit

- [ ] **T018** 跑 pre-commit 全量检查
  - `cd /Users/yihan_guo/Desktop/旅居产品 && pre-commit run --all-files`
  - 期望：13 道关卡全部 Pass

- [ ] **T019** [P] 浏览器实测（手动验证 SC-006）
  - 搜「上海露营地」→ 卡片全是上海 ✅
  - 搜「莫干山自驾」→ 卡片全是莫干山一带 ✅
  - 搜「漠河」→ 显示空状态文案 ✅
  - 搜「露营」→ 杭州周边（行为不变）✅

- [ ] **T020** Commit 改动到 `fix/bug-2-source-filter` 分支
  - commit message：`FIX: 来源点位按搜索词地理意图过滤 (#001)`
  - 触发 pre-commit + commit-msg hook
  - 期望：13 道关卡全过 + commit 进入 fix 分支

- [ ] **T021** 合并 fix 分支到 main
  - `cd /Users/yihan_guo/Desktop/旅居产品 && git merge --no-ff fix/bug-2-source-filter`
  - 期望：fast-forward 或干净 merge commit

---

## 依赖关系图

```
T001 (setup)
  ↓
T002 (test geocode) → T003 (impl geocode)
                       ↓
                       T009 needs T003
  ↓
T004 (test US1) → T005 (impl q+detect) → T006 (metadata) → T007 (cache key)
                                            ↓
                                            T008 (test US2) → T009 (impl amap fallback)
                                            ↓
                                            T010 (test US3) → T011 (verify pass)
                                            ↓
                                            T012 (test cache)
  ↓
T013, T014, T015, T016 (frontend) → T017 (tsc check)
  ↓
T018 (pre-commit) → T019 (browser) → T020 (commit) → T021 (merge)
```

---

## 总数

- **21 个 task**
- **5 个并行机会**（[P] 标记）—— 实际不太用得到（你独立开发，串行做最简单）
- **预计总时长**：2-3 小时（含浏览器实测）

---

## 完成标准（来自 spec.md SC-001 ~ SC-007）

| SC | 验证方式 | 哪个 task |
|---|---|---|
| SC-001 上海 100% | T019 浏览器实测 | T019 |
| SC-002 莫干山 100% | T019 浏览器实测 | T019 |
| SC-003 漠河空状态 | T008 + T019 | T008, T019 |
| SC-004 露营 0 回归 | T010 测试 + T019 实测 | T010, T019 |
| SC-005 4 条 regression test | T002/T004/T008/T010/T012 | 累计 4 条以上 |
| SC-006 演示 3 次无错 | T019 | T019 |
| SC-007 cache 7 天 | T012 | T012 |
