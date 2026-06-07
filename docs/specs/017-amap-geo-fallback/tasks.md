---

description: "Tasks for spec-017: 搜索地理意图识别 amap geocoding 兜底"
---

# Tasks: 搜索地理意图识别 amap geocoding 兜底

**Input**: Design documents from `/specs/017-amap-geo-fallback/`

**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/search-api.md

**Tests**: Included（按 CLAUDE.md 工作流约定：新功能至少 1 条 happy-path pytest；本 spec 改后端核心逻辑，加 4 个 case 防回归）

**Organization**: Tasks grouped by user story；US1/US2 是 P1（MVP）、US3 是 P2（性能护栏）。

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)
- Include exact file paths

## Path Conventions

- **Backend (Python/FastAPI)**: `backend/app/`, `backend/tests/`
- **Frontend (Taro/React)**: `frontend/src/`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: 确认环境就绪（spec-017 不需要新依赖 / 新目录）

- [ ] T001 在主仓确认当前分支 `017-amap-geo-fallback`、`git status` 干净（如有 spec 文档残留差异先 commit 到本分支）

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: 所有 US 共享的基础类型 / 工具函数（必须先就位）

**⚠️ CRITICAL**: US1/US2/US3 都依赖这些、必须先完成

- [ ] T002 [P] 在 `backend/app/routers/search.py` 顶部加导入：`from dataclasses import dataclass`, `from typing import Literal`, `import re`, `import time`，并 import `geocode_query` from `app.services.amap_service`
- [ ] T003 [P] 在 `backend/app/routers/search.py` 加 `GeoResolution` dataclass（参考 data-model.md：字段 lat / lon / formatted_name / source / latency_ms / cache_hit）
- [ ] T004 [P] 在 `backend/app/routers/search.py` 加 query 归一化函数 `_normalize_query(q: str) -> str`（实现：`re.sub(r'\s+', ' ', q.strip())`，保留中文不 lowercase）
- [ ] T005 [P] 在 `backend/app/routers/search.py` 加 negative cache helpers：`_amap_negative_cache_get(query_normalized) -> bool` / `_amap_negative_cache_set(query_normalized) -> None`（cache key: `amap:geocode:negative:{md5}`，TTL=86400，使用 `app.services.cache.cache_get/cache_set`）
- [ ] T006 在 `frontend/src/types.ts` 把 `WarningCode` 类型 alias 扩展（如果尚不存在则新加）：`'extract_timeout' | 'extract_json_error' | 'extract_other' | 'network_error' | 'unrecognized_location'`

**Checkpoint**: Foundation ready - 可以开始 US 实施

---

## Phase 3: User Story 1 - 任何地名都能正确定位 (Priority: P1) 🎯 MVP

**Goal**: 字典未命中时自动调 amap geocoding、命中后 search API 用 amap 返回的坐标作 search_center；前端地图视野跳到识别到的城市。

**Independent Test**: 真机搜「景德镇露营地」→ 地图视野跳到江西景德镇市、`source_breakdown.search_center_source == 'amap'`、AI 返回景德镇本地内容（quickstart.md Case 2）

### Tests for User Story 1

- [ ] T007 [P] [US1] 在 `backend/tests/test_search_geo_fallback.py` 写 `test_dict_hit_no_amap_call`：query=「南昌露营地」（字典已有「南昌」），mock `app.services.amap_service.geocode_query` → 断言**未被调用**；响应 `source_breakdown.search_center_source == 'dict'`、`search_center.lat ≈ 28.68`
- [ ] T008 [P] [US1] 在 `backend/tests/test_search_geo_fallback.py` 写 `test_amap_fallback_hit`：query=「景德镇露营地」（字典没收），mock `geocode_query` → `(29.27, 117.18, "江西省景德镇市")`；断言 `source_breakdown.search_center == {"lat": 29.27, "lon": 117.18}`、`detected_place == "江西省景德镇市"`、`search_center_source == 'amap'`

### Implementation for User Story 1

- [ ] T009 [US1] 在 `backend/app/routers/search.py` 实现 `_resolve_search_center_for_query(query: str, fallback_lat: float, fallback_lon: float) -> GeoResolution` 异步函数，三段式：
  1. 空 query / 无 strip 后内容 → 返回 fallback + source='no_place_token'
  2. 字典命中（`detect_place_center` 返回非 None）→ 返回 dict + 字典坐标
  3. 字典未命中 → 调 amap（见 Phase 4 T013 补 amap 路径）
  - 记录 latency_ms（time.perf_counter）
  - 每次调用记一行结构化日志 `logger.info('geo_resolve', extra={...})`（按 data-model.md 字段）
- [ ] T010 [US1] 修改 `backend/app/routers/search.py:unified_search` 函数（约 230-289 行）：
  - 把原 `detected = detect_place_center(payload.q, tokens)` + if/else 块替换为 `resolution = await _resolve_search_center_for_query(payload.q, payload.lat, payload.lon)`
  - `effective_lat = resolution.lat`、`effective_lon = resolution.lon`、`detected_name = resolution.formatted_name`
  - 保留原 DB / AI 兜底链路不变
- [ ] T011 [US1] 在 `backend/app/routers/search.py` 的 `unified_search` 响应里把 `source_breakdown` 加上 `"search_center_source": resolution.source`（dict/amap/no_place_token）
- [ ] T012 [US1] 跑 `cd backend && pytest tests/test_search_geo_fallback.py::test_dict_hit_no_amap_call tests/test_search_geo_fallback.py::test_amap_fallback_hit -v`，确保 T007/T008 通过

**Checkpoint**: US1 完成——字典快路径 + amap 兜底命中工作

---

## Phase 4: User Story 2 - 识别不到地名时明确报错 (Priority: P1)

**Goal**: amap 也识别不到时返回 `warning_code='unrecognized_location'`、不悄悄 fallback 杭州；前端不动地图视野 + 显示明确报错。

**Independent Test**: 真机搜「火星二号营地」→ 地图视野**不变**、显示「无法识别地名」文案、底库无杂数据（quickstart.md Case 3）

### Tests for User Story 2

- [ ] T013 [P] [US2] 在 `backend/tests/test_search_geo_fallback.py` 写 `test_amap_fallback_miss_returns_unrecognized`：query=「火星二号营地」（字典 miss），mock `geocode_query` → None；断言 `warning_code == 'unrecognized_location'`、`source_breakdown.search_center is None`、`spots == []`、`unmapped_candidates == []`、不调 AI（`provider.llm == "none"`）
- [ ] T014 [P] [US2] 在 `backend/tests/test_search_geo_fallback.py` 写 `test_amap_timeout_treated_as_unrecognized`：mock `geocode_query` → raises `httpx.TimeoutException`（或 `asyncio.TimeoutError`）；断言 `warning_code == 'unrecognized_location'`
- [ ] T015 [P] [US2] 在 `backend/tests/test_search_geo_fallback.py` 写 `test_negative_cache_skips_amap_on_repeat`：第 1 次调 mock geocode_query 返回 None；第 2 次同 query 调用、断言 mock **未被再次调用**（`assert_called_once()`）；验 negative cache 工作

### Implementation for User Story 2

- [ ] T016 [US2] 在 `backend/app/routers/search.py:_resolve_search_center_for_query` 补 amap 路径（接 T009 的 step 3）：
  - 调用前先 `if await _amap_negative_cache_get(normalized): return GeoResolution(None, None, None, 'none', latency_ms, cache_hit=True)`
  - 调 `geocode_query(query)`（不传 province hint——search API 不知道用户在哪个省）
  - 命中 → `return GeoResolution(lat, lon, name, 'amap', latency_ms, cache_hit=False)`
  - 未命中 / 异常 / timeout → 写 `await _amap_negative_cache_set(normalized)`，`return GeoResolution(None, None, None, 'none', latency_ms, cache_hit=False)`
- [ ] T017 [US2] 在 `backend/app/routers/search.py:unified_search` 加 unrecognized_location 短路：
  - 在 `_resolve_search_center_for_query` 返回后立即检查 `if resolution.source == 'none':` → return early 响应（不查 DB、不调 AI），按 contracts/search-api.md Case 3 schema 返回
  - warning 文案：`f"无法识别您输入的地名「{payload.q}」，请尝试更明确的地名（如「南昌露营地」「莫干山民宿」）"`
  - warning_code = 'unrecognized_location'
  - source_breakdown 含 detected_place=None, search_center=None, search_center_source='none', strategy='unrecognized_location'
- [ ] T018 [P] [US2] 修改 `frontend/src/pages/index/index.tsx` 的 complete 事件 handler（约 237-257 行）：
  - 在原读 `source_breakdown.search_center` 那段（spec-016 修复的位置）外层加判断：
    ```ts
    if (data.warning_code === 'unrecognized_location') {
      // 不调 setSearchCenter（保持视野）
      // setAiCandidates([]) 已经会被 data.spots=[] 覆盖
      // setUnmapped([]) 也已经被 data.unmapped_candidates=[] 覆盖
      // setWarning 和 setWarningCode 已经在前面处理
      // 不启动 polling（data.extract_pending=false 自然不会触发）
    } else {
      const sb = (data as any).source_breakdown
      if (sb?.search_center) {
        setSearchCenter({ ... })
      }
    }
    ```
- [ ] T019 [P] [US2] 在 `frontend/src/pages/index/index.tsx` 或 `components/AnswerPanel.tsx` 验证 warning 文案能正常展示（当前 AnswerPanel 已读 warningCode、应该已经能展示，仅做核验、不强制改）
- [ ] T020 [US2] 跑 `cd backend && pytest tests/test_search_geo_fallback.py::test_amap_fallback_miss_returns_unrecognized tests/test_search_geo_fallback.py::test_amap_timeout_treated_as_unrecognized tests/test_search_geo_fallback.py::test_negative_cache_skips_amap_on_repeat -v`，确保 T013-T015 通过

**Checkpoint**: US2 完成——unrecognized_location 全链路工作

---

## Phase 5: User Story 3 - 字典快路径性能不退化 (Priority: P2)

**Goal**: 字典命中和「无 place_token」的 query 不调 amap、不影响响应时间。

**Independent Test**: 连续搜「南昌露营地」10 次、`grep "geo_resolve.*amap" uvicorn.log` 应为 0 行（quickstart.md Step 5 Query B 后端日志验证）

### Tests for User Story 3

- [ ] T021 [P] [US3] 在 `backend/tests/test_search_geo_fallback.py` 写 `test_no_place_token_keeps_user_location_no_amap`：query=「免费露营地」（全是 generic_token），mock `geocode_query`；断言 amap 未被调用、`search_center == {lat: payload.lat, lon: payload.lon}`、无 warning_code

### Implementation for User Story 3

- [ ] T022 [US3] 在 `_resolve_search_center_for_query` 字典 miss 后、调 amap 前加 `_split_tokens` 检查：
  ```python
  place_tokens, _ = _split_tokens(tokens)
  if not place_tokens:
      return GeoResolution(fallback_lat, fallback_lon, None, 'no_place_token', latency_ms, cache_hit=False)
  ```
  保证「免费露营地」「附近驻车点」这种 query 不调 amap、不报错
- [ ] T023 [US3] 跑 `cd backend && pytest tests/test_search_geo_fallback.py::test_no_place_token_keeps_user_location_no_amap -v`，确保 T021 通过

**Checkpoint**: US3 完成——性能护栏到位

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: 全量回归 + 真机验收 + 文档沉淀

- [ ] T024 跑 `cd backend && /Users/yihan_guo/Desktop/异想天开/旅居产品_副本/.venv/bin/python -m pytest tests/ -x` 全量回归（应 97 passed = 94 现有 + 3 新；特别盯 `test_q_unknown_city_amap_fallback` 和 `test_q_no_geo_intent_keeps_user_location` 必须通过——places.py 行为零回归）
- [ ] T025 重启后端 uvicorn（venv Python、`--host 0.0.0.0:8000`，命令见 quickstart.md Step 1）
- [ ] T026 跑 quickstart.md Step 2 三条 curl（Case 1 字典/Case 2 amap/Case 3 unrecognized），断言响应字段符合 contracts/search-api.md schema
- [ ] T027 `cd frontend && TARO_APP_API_BASE=http://$(ipconfig getifaddr en0):8000 npm run build:weapp`，构建 weapp dist
- [ ] T028 用户真机验证 SC-006 三条 query：
  - Query A「景德镇露营地」→ ✓ 视野跳景德镇 / ✓ AI 返回江西内容 / ✓ marker 落到景德镇
  - Query B「莫干山民宿」→ ✓ 字典命中（后端日志 source=dict）/ ✓ 视野跳莫干山
  - Query C「火星二号营地」→ ✓ 视野不动 / ✓ 显示明确报错 / ✓ 无杂 marker
- [ ] T029 如真机有不通过项目→调试 / 修复 / 回到对应 US 任务；全过 → 把 US1/US2/US3 标记为「真机验证通过」
- [ ] T030 [P] 更新 `docs/PM学技术.md`（用户授权后）加 3 个词条：amap geocoding / negative cache / fallback chain（含「优雅降级」概念）
- [ ] T031 [P] 更新记忆 `~/.claude/projects/.../memory/current_progress.md`：spec-017 状态从 in_progress → ✅ 已合并 main；下一步 MVP 候选只剩 7.2 UGC 和 spec-006 Phase 2

---

## Dependencies & Execution Order

```
Phase 1 (Setup)
    ↓
Phase 2 (Foundational) — T002-T006 全部 [P] 可并行
    ↓
Phase 3 (US1) ─┐
Phase 4 (US2) ─┼─→ US1/US2/US3 内部测试 [P] 可并行；实施任务有顺序依赖
Phase 5 (US3) ─┘   (US2 实施依赖 US1 的 T009 _resolve_search_center_for_query 骨架)
    ↓
Phase 6 (Polish) — T030/T031 可并行
```

**关键依赖**：
- US1 T009 的 resolver 函数骨架是 US2 T016（补 amap 路径）的前置
- US3 T022（_split_tokens 检查）插在 US1 T009 字典 miss 后、US2 T016 amap 之前
- 实际推荐串行：US1 → US3 → US2（按 resolver 的三段式顺序写代码最自然）

## Parallel Opportunities

- **Phase 2**：T002/T003/T004/T005/T006 全部 [P]（5 个独立任务，可一次性写完）
- **Phase 3 测试**：T007/T008 [P]（不同测试函数）
- **Phase 4 测试**：T013/T014/T015 [P]
- **Phase 4 前端**：T018/T019 [P]（不同文件）
- **Phase 6 文档**：T030/T031 [P]

## MVP Scope

按 spec.md 优先级：
- **MVP = US1 + US2**（两个都是 P1）= Phase 3 + Phase 4 = ~12 任务
- US3 是 P2 性能护栏、可在 MVP 后追加

但本 spec 因为代码相互嵌套（resolver 函数本身就需要包含三段式逻辑）、**实际实施按 Phase 顺序一次性完成最高效**。

## Format Validation

✓ 所有任务都符合 `- [ ] T### [P?] [Story?] description with file path` 格式
✓ Setup（T001）/ Foundational（T002-T006）/ Polish（T024-T031）无 Story 标签
✓ Phase 3-5 全部带 [US1]/[US2]/[US3] 标签
✓ 31 个任务、每个都有具体文件路径
