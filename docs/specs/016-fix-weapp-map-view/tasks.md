---
description: "Task list for 016-fix-weapp-map-view"
---

# Tasks: 修复微信小程序真机地图初始视野不居中

**Input**: Design documents from `/specs/016-fix-weapp-map-view/`

**Prerequisites**: plan.md, spec.md, research.md, quickstart.md

**Tests**: 无自动化测试任务——前端无单测设施。验收靠**真机调试人工核验**（spec 关键约束：模拟器不算数）。

**Organization**: 任务按用户故事分组。本功能 3 个故事均为 P1，且由同一处视野逻辑修复同时满足——故核心修复为 Foundational，US1~US3 阶段为真机核验。

## Format: `[ID] [P?] [Story] Description`

---

## Phase 1: Setup

本功能无项目初始化需求——前端工程、依赖、`016-fix-weapp-map-view` 分支均已就绪。无 Setup 任务。

---

## Phase 2: Foundational (核心修复 —— 阻塞所有用户故事)

**Purpose**: 实现地图视野控制修复。一处改动同时服务 US1（初始居中）/ US2（跟随更新）/ US3（崩溃护栏保留）

**⚠️ CRITICAL**: 本阶段完成前，US1~US3 无法核验

- [X] T001 在 `frontend/src/components/MapCanvas.weapp.tsx` 实现视野修复——主选方案 B：视野目标（用户定位 / 搜索中心 / 点位包围盒）变化时，通过 React `key` 让 `<Map>` 重新挂载，使其带当前 `longitude/latitude/scale` 重新渲染一次（绕开「声明式经纬度挂载后改值不生效」）；`include-points` 保持非空崩溃护栏（设为目标包围盒或保留 `CRASH_GUARD_POINTS` 常量，不得退回空数组）；保留并加 vConsole 诊断日志输出计算出的视野目标，便于首轮真机测同时核实根因（research.md D1/D2/D4）
- [X] T002 [P] 构建验证——`cd frontend && npm run build:weapp` 与 `npm run build:h5` 均成功、无报错

**Checkpoint**: 代码改动 + 构建通过——可进入真机核验

---

## Phase 3: User Story 1 - 初始定位地图居中 (Priority: P1)

**Goal**: 真机上初始定位成功后地图视野居中到用户位置

**Independent Test**: 真机调试打开小程序，定位成功后地图画面中心在用户实际位置，定位蓝点居中可见

- [X] T003 [US1] 真机调试人工核验——打开小程序、定位成功后，地图画面居中到用户位置；定位蓝点与画面中心一致（per [quickstart.md](./quickstart.md) 第二节「初始居中」；对应 SC-001 / SC-003）

**Checkpoint**: US1——初始居中真机核验通过

---

## Phase 4: User Story 2 - 视野跟随定位/搜索更新 (Priority: P1)

**Goal**: 定位坐标更新、搜索返回结果后，地图视野跟随到对应目标

**Independent Test**: 真机上定位由兜底坐标更新为真实坐标后地图跟随；搜索出点位后地图移动到点位范围

- [ ] T004 [US2] 真机调试人工核验——定位坐标更新后视野跟随；搜索出点位 / 搜索到地名无点位 两种情况视野各自移动到位（per quickstart 第二节「更新跟随」；对应 SC-002）

**Checkpoint**: US2——视野跟随真机核验通过

---

## Phase 5: User Story 3 - 不引入 `<map>` 崩溃回归 (Priority: P1)

**Goal**: 修视野的改动不重新触发 spec-014 的 `<map>` 渲染崩溃

**Independent Test**: 真机上地图加载、定位、搜索、拖动全程无崩溃

- [X] T005 [US3] 真机调试人工核验——地图加载、定位、搜索、拖动全程无 `<map>` 渲染崩溃（spec-014 的 `Cannot read property 'lat'` 不复现；对应 SC-004）

**Checkpoint**: US3——无崩溃回归真机核验通过

---

## Phase 6: Polish & 迭代

- [ ] T006 真机核验边界——拒绝定位授权时地图居中到兜底默认坐标、不崩；H5 端地图人工核验零回归（per quickstart 第二节边界 + 第三节；对应 SC-005 / FR-004）
- [ ] T007 **迭代任务（条件触发）**——若 T003~T006 任一真机核验未通过：按 research.md 备选方案 C（命令式 `MapContext.moveToLocation`）调整 `MapCanvas.weapp.tsx`，重新构建并请用户真机复验；循环至全部核验通过
- [X] T008 核验通过后——移除 T001 加的 vConsole 临时诊断日志，重新 `build:weapp` 确认

---

## Dependencies & Execution Order

- **T001**（核心修复）→ **T002**（构建）→ **T003~T006**（真机核验，用户在一次真机调试会话里可一起做）
- **T007**：仅当 T003~T006 有失败时触发；迭代后回到 T002 重新构建+核验
- **T008**：所有真机核验通过后做收尾

## Implementation Strategy —— 真机迭代循环

本 bug 的修复**无法靠开发者自测完成**——原生 `<map>` 视野行为真机与模拟器不一致，必须真机验收。流程：

1. **T001**：实现方案 B（一处代码改动）
2. **T002**：构建
3. **用户真机调试**：按 quickstart 核验 T003~T006
4. **通过** → T008 收尾 → 完成
5. **不通过** → T007 按方案 C 迭代 → 回第 2 步

→ 「我改一版 → 你真机测 → 再改」的循环，直到真机核验全过。开发者每轮只能提交一版改动 + 构建，真机结果由用户反馈。

## Notes

- 核心修复（T001）是一处改动、同时满足 US1/US2/US3——故 US1~US3 阶段只有真机核验任务，无各自的实现任务。
- spec 关键约束：根因真机核实再定方案——T001 内置 vConsole 诊断日志，让首轮真机测同时回答 research.md「待真机核实的关键问题」。
- 「修好了」只以真机调试为准；微信开发者工具模拟器表现不作通过依据。
- 不含「真机搜索连不上后端」那个独立的基础设施问题。
