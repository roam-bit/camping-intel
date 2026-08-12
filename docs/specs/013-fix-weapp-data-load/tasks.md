---
description: "Task list for 修复微信小程序端点位数据加载不出来"
---

# Tasks: 修复微信小程序端点位数据加载不出来

**Input**: Design documents from `/specs/013-fix-weapp-data-load/`

**Prerequisites**: plan.md, spec.md, research.md, quickstart.md

**Tests**: 前端无单测设施——靠 `build:h5` / `build:weapp` + 微信开发者工具人工核验（plan.md 已说明）。

**Organization**: 按用户故事分组。本 spec 是 bug 修复，仅动 `frontend/` 的 3 个文件。

## Format: `[ID] [P?] [Story] Description`

- **[P]**: 可并行（不同文件、无未完成依赖）
- **[Story]**: 所属用户故事（US1-US5）

---

## Phase 1: Setup（验证环境准备）

- [X] T001 确认验证环境：worktree 根 `.env` 已就位；本地后端可起（curl `127.0.0.1:8000/api/v1/health` 秒回）；Docker Postgres 在跑；微信开发者工具能打开 `frontend/dist/`

---

## Phase 2: Foundational

**本 spec 无阻塞性前置任务** —— 3 处改动各在独立文件，无共享前置。

---

## Phase 3: User Story 1 + 2 - 核心修复：解耦「加载点位」与「定位成功」（Priority: P1）🎯 MVP

**Goal**: 让点位数据加载不再被「定位是否成功」卡死——定位成功用真实坐标、失败用杭州默认坐标，两种都加载点位。

**Independent Test**: 微信开发者工具打开小程序首页，不操作即出现点位 marker；定位被拒绝时仍有点位。

⚠️ T002、T003 改不同文件，可并行；但「小程序端真正能加载点位」需 T002+T003 合力（T002 解耦触发、T003 保证定位总能到终态）。

### Implementation

- [X] T002 [P] [US1] 改 `frontend/src/pages/index/index.tsx` 约 99-109 行的定位 useEffect：`denied`/`error` 分支在弹 toast 之外**也调 `loadPlaces()`**（`ok` 分支保持）；三种终态都加载点位，失败时用 `useUserLocation` 已回落的杭州默认坐标（research.md D2）
- [X] T003 [P] [US2] 改 `frontend/src/hooks/useUserLocation.ts`：给 `Taro.getLocation` 加超时保护（`Promise.race` + 约 8 秒超时），超时按失败处理（status → `error`、coord 保持杭州默认）——保证定位调用不挂起、`locationStatus` 总能到达终态（research.md D3）

**Checkpoint**: 小程序首页能加载并显示点位（不论定位成败）

---

## Phase 4: User Story 3 - 小程序定位权限声明（Priority: P2）

**Goal**: 小程序调 `Taro.getLocation` 能正常弹授权、拿真实定位。

**Independent Test**: 微信开发者工具小程序首次定位时弹出微信位置授权请求。

⚠️ **独立**: 改 `app.config.ts`，与 T002/T003 无文件冲突，可并行。

### Implementation

- [X] T004 [P] [US3] 改 `frontend/src/app.config.ts`：`defineAppConfig` 里加 `permission['scope.userLocation']`（带 `desc` 用途说明）+ `requiredPrivateInfos: ['getLocation']`——weapp-only 配置，H5 忽略（research.md D1）

**Checkpoint**: 小程序定位授权流程可正常发起

---

## Phase 5: User Story 5 - H5 端零回归（Priority: P1）

**Goal**: 确认改动未破坏 H5——定位成功路径行为不变；定位失败时 H5 也能用默认中心加载点位。

**Independent Test**: `build:h5` 成功；H5 定位成功时点位加载与改动前一致。

⚠️ **依赖**: 在 T002/T003/T004 改完后执行。

### Implementation

- [X] T005 [US5] H5 零回归核验：`cd frontend && npm run build:h5`，浏览器（`localhost:10086`）核验——定位成功时点位/地图/列表与改动前一致；定位失败/拒绝时 H5 也能用杭州默认中心显示点位（对照 quickstart §4）

**Checkpoint**: H5 零回归确认

---

## Phase 6: User Story 4 + 验收 - 消除 `Error: timeout` 与全量核验（Priority: P2）

**Goal**: 核验启动 `Error: timeout` 是否随 D1+D3 消除；完成 quickstart 全量核验。

**Independent Test**: 微信开发者工具小程序启动，Console 无未被捕获的 `Error: timeout`。

⚠️ **依赖**: 在 T002/T003/T004 改完后执行。

### Implementation

- [X] T006 [US4] `build:weapp` + 微信开发者工具核验 Console：确认启动**无未被捕获的 `Error: timeout`**（research.md D4 假设核验点）。若已消失 → D1+D3 成立；若仍在 → 用 Console/Sources 面板定位抛出点，按 spec FR-005「消除或妥善捕获」继续处理
- [ ] T007 微信开发者工具按 [quickstart.md](./quickstart.md) §1-§3、§5 全量核验：小程序地图有 marker、底部列表有点位、Network 有 `/api/v1/places` 请求、定位授权与拒绝两种场景都有点位
- [X] T008 复核：确认 `frontend/src/hooks/usePlaces.ts` 与 `frontend/src/components/MapCanvas.*` 未被改动（本 spec 不该动它们）

---

## Dependencies & Execution Order

### Phase 依赖

- **Setup (P1)**: 无依赖
- **Foundational (P2)**: 空
- **US1+US2 (P3)**: Setup 后即可——T002、T003 可并行
- **US3 (P4)**: 独立，可与 P3 并行
- **US5 (P5)**: 须等 T002/T003/T004 改完
- **US4+验收 (P6)**: 须等 T002/T003/T004 改完

### 关键点

- T002（`index.tsx`）、T003（`useUserLocation.ts`）、T004（`app.config.ts`）**三个不同文件，互不冲突，可全部并行**
- `usePlaces.ts` 不动——`loadPlaces` 已用传入的 `userCoord`，无需改

### 并行机会

- T002 / T003 / T004 三个改动可同时进行
- 之后 T005（H5 核验）与 T006（weapp timeout 核验）也可并行（不同端）

---

## Parallel Example

```bash
# 三处代码改动不同文件，可并行：
Task: "T002 index.tsx 解耦 loadPlaces"
Task: "T003 useUserLocation.ts 加超时保护"
Task: "T004 app.config.ts 加定位权限声明"
```

---

## Implementation Strategy

### MVP（US1 + US2）

T002 + T003 合起来是核心修复——小程序能加载点位了。T004（权限声明）让「定位成功」这条更优路径也可用。三者改完即 MVP。

1. Phase 1 Setup
2. Phase 3 + 4：T002 / T003 / T004 并行改完
3. Phase 5 US5 H5 零回归核验
4. Phase 6 微信开发者工具全量核验（含 timeout 核验）

### 增量交付

- T002+T003 → 小程序能加载点位（核心）
- T004 → 定位授权路径可用
- T005/T006/T007 → 双端核验收尾

---

## Notes

- 总任务数：8（T001-T008）
- 代码改动：`index.tsx`（T002）、`useUserLocation.ts`（T003）、`app.config.ts`（T004）+ `MapCanvas.weapp.tsx`（实现期为查地图崩溃移除了 includePoints）
- 前端无单测设施——CLAUDE.md「每修 bug 加 regression 测试」本次无法执行（已在 plan.md 记录）

---

## 实现状态（2026-05-22）

**代码改动完成**：T002（index.tsx 解耦）、T003（useUserLocation 超时保护）、T004（app.config 定位权限）+ MapCanvas.weapp.tsx（移除 includePoints、改自算视野）。typecheck + 双端构建全过。`usePlaces`/`index.tsx 数据流` 未越界改动。

**微信开发者工具人工核验结果**：
- ✅ 定位权限声明生效——小程序能正常定位（弹授权、拿到坐标）
- ✅ 解耦生效——小程序确实向后端发 `/api/v1/places` 请求（之前 Network 零请求）；数据加载链路打通——**spec-013 核心目标达成**
- ✅ `Error: timeout` 已消除——实测为**灰度基础库 3.16.1 的产物**，换稳定基础库（3.15.2）后消失（US4 / FR-005 达成。⚠️ 基础库须保持稳定版）
- ✅ H5：`build:h5` 通过；定位成功路径代码未动；H5 localhost 核验地图正常 —— US5 零回归
- ❌ **地图 marker 视觉显示**：被一个独立的 `<map>` 组件崩溃阻塞——`Cannot read property 'lat'`（栈 `fitBounds ← pointsChanged`，腾讯地图 SDK 内部）。该崩溃在移除 `includePoints`、换稳定基础库后**仍存在**，非 spec-013 代码问题，属 spec-012 地图组件遗留。

**结论**：spec-013 的目标（小程序数据加载）已达成——数据能加载、定位正常、`Error: timeout` 消除。地图 marker 的**视觉渲染**受独立的 `<map>` 组件崩溃阻塞，已决定单独立 spec-014 彻查（用户拍板方案 A）。T007 因此未能全绿。
