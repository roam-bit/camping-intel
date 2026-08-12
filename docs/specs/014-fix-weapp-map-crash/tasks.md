---
description: "Task list for 014-fix-weapp-map-crash"
---

# Tasks: 彻查并修复微信小程序地图 marker 渲染崩溃

**Input**: Design documents from `/specs/014-fix-weapp-map-crash/`

**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, quickstart.md ✅（无 data-model.md / contracts/）

**Tests**: 不含自动化测试任务——前端无单测设施（plan.md Constitution Check 已记录），验证靠双端构建 + 微信开发者工具人工核验。

**Organization**: 按 user story 分组。本 spec 改动面极小（1 个前端文件），任务有意保持精简。

## Format: `[ID] [P?] [Story] Description`

- **[P]**: 可并行（不同操作、无相互依赖）
- **[Story]**: 所属 user story（US1 / US2）

---

## Phase 1: Setup

无 Setup 任务——本 spec 是单文件 bug 修复，不涉及项目初始化。

## Phase 2: Foundational

无 Foundational 任务——无阻塞性前置。根因调查已在 research.md 完成（已验证机制 + 证据分级）。

---

## Phase 3: User Story 1 - 小程序地图正常显示点位 marker（Priority: P1）🎯 MVP

**Goal**: 微信小程序首页地图加载点位时不再渲染层崩溃，marker 正常显示并可点击。

**Independent Test**: 微信开发者工具打开小程序首页（区域有点位），地图出现 marker，Console 无 `Cannot read property 'lat'` 崩溃。

### Implementation for User Story 1

- [X] T001 [US1] 修改 `frontend/src/components/MapCanvas.weapp.tsx`：(a) 始终向 `<Map>` 传 `includePoints`，并保证它永远是 ≥2 个有效坐标点的非空数组——有 marker 用各 marker 坐标，marker 数 < 2 时用「围绕中心点（搜索中心 / 用户定位 / 杭州默认，按优先级）的合成点」补齐到 ≥2；(b) 删除 `viewForMarkers()` 函数与受控 `view` state，地图视野改由 `includePoints` 单一驱动，`<Map>` 的 `longitude/latitude` 仅留初始中心值。依据 research.md D1/D2。
- [X] T002 [US1] 在 `frontend/` 跑 `build:weapp`，确认构建通过、无编译错误（TypeScript / Taro）。
- [ ] T003 [US1] 微信开发者工具人工核验（quickstart.md A/B/C）：① 地图渲染、Console 无 `Cannot read property 'lat'` 崩溃；② 0 / 1 / 多个点位三种数量都不崩；③ marker 可见且点击能打开点位详情。

**Checkpoint**: 小程序地图 marker 能显示、不崩溃——spec-014 主目标达成。

---

## Phase 4: User Story 2 - H5 端零回归（Priority: P1）

**Goal**: 本次修改不破坏 H5 端地图。

**Independent Test**: `build:h5` 成功；H5 首页地图、marker、交互与改动前肉眼一致。

### Implementation for User Story 2

- [X] T004 [P] [US2] 在 `frontend/` 跑 `build:h5`，确认构建通过、无编译错误。
- [ ] T005 [US2] H5 人工核验（quickstart.md D）：首页地图、marker、点击交互、搜索后自动飞到结果范围——与改动前一致、无回归。

**Checkpoint**: weapp 修复达成且 H5 零回归——两个 P1 user story 均完成。

---

## Phase 5: Polish

- [ ] T006 全部核验通过后，更新 `specs/014-fix-weapp-map-crash/research.md` 的「最大不确定性」一项为「已运行时核验」，闭合「强推断 → 已验证」的证据链（对应 SC-006）。

---

## Dependencies & Execution Order

- **T001**（核心修复）→ 阻塞所有后续任务。
- **T002**（weapp 构建）依赖 T001；**T003**（小程序核验）依赖 T002。
- **T004**（H5 构建）依赖 T001，可与 T002 并行；**T005**（H5 核验）依赖 T004。
- **T006**（收尾文档）依赖 T003 + T005 全部通过。

执行顺序：T001 → (T002 ∥ T004) → (T003、T005) → T006。

## Parallel Opportunities

- T002（build:weapp）与 T004（build:h5）在 T001 完成后可并行——不同构建目标、互不影响。

## Implementation Strategy

MVP = User Story 1（Phase 3）：T001 修复 → T002 构建 → T003 核验，小程序地图即可用。User Story 2 是零回归校验，与 US1 共用同一处代码改动（T001），构建/核验阶段独立。

## Notes

- 本 spec 不含自动化测试任务：前端无单测设施，CLAUDE.md「每修 bug 加 regression 测试」因此无法执行（plan.md 已记录，与 spec-009/010/012/013 一致）。
- T003 / T005 为人工核验任务，需在微信开发者工具 / 浏览器中由人执行。
- 微信开发者工具基础库须用稳定版（非灰度版）——见 quickstart.md 前置。
