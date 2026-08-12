---
description: "Task list for 015-ai-content-label"
---

# Tasks: AI 生成内容应用内合规标识

**Input**: Design documents from `/specs/015-ai-content-label/`

**Prerequisites**: plan.md, spec.md, research.md, quickstart.md

**Tests**: 无自动化测试任务——本功能为纯前端 UI 文案改动，项目前端无单测设施（与 spec-009/010/012 一致）。验证靠双端构建 + 人工核验（见 Phase 5 / 6）。

**Organization**: 任务按用户故事分组。本功能 3 个故事均为 P1。

## Format: `[ID] [P?] [Story] Description`

- **[P]**: 可并行（不同文件、无未完成依赖）
- **[Story]**: US1 / US2 / US3，对应 spec.md 的用户故事

---

## Phase 1: Setup

本功能无项目初始化需求——前端工程、依赖、`015-ai-content-label` 分支均已就绪，无新增第三方依赖。无 Setup 任务，直接进入 Foundational。

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: 创建被 US1 与 US2 共用的合规文案组件与样式

**⚠️ CRITICAL**: 本阶段完成前，US1 / US2 无法开始

- [X] T001 创建共享组件 `frontend/src/components/AiContentLabels.tsx`——导出 `AiGeneratedTag`（显式标识，渲染文案「AI 生成整理」）与 `AiRiskNotice`（风险提示，渲染「内容仅供参考，请出行前自行核实」之意）两个组件；合规文案集中在此文件，作为全站单一来源（research.md D1）
- [X] T002 [P] 在 `frontend/src/pages/index/index.css` 新增 `AiGeneratedTag` 与 `AiRiskNotice` 的样式——复用既有 `ai-gen-chip` 视觉风格；标识小而可辨、不压过点位名等核心信息；只用真实标签/类选择器，**禁用 `*` 通配符选择器**（遵 spec-010 WXSS 编译教训）

**Checkpoint**: 共享组件与样式就绪——US1、US2 可并行开始

---

## Phase 3: User Story 1 - 用户能看出点位信息是 AI 生成的 (Priority: P1) 🎯 MVP

**Goal**: 在所有展示 AI 生成内容的界面位置插入「AI 生成整理」显式标识

**Independent Test**: 完成一次搜索，AI 提炼结果区、点位卡片（紧凑+完整）、点位详情、来源线索卡上都能看到「AI 生成整理」标识

### Implementation for User Story 1

- [X] T003 [P] [US1] `frontend/src/components/AnswerPanel.tsx`——在 AI 提炼结果区插入 `<AiGeneratedTag />`（既有标题「AI 提炼结果」可保留不改，标识插入即满足 FR-008）
- [X] T004 [P] [US1] `frontend/src/components/PlaceCard.tsx`——在点位卡片插入 `<AiGeneratedTag />`；紧凑与完整两模式共用此组件，一处即覆盖两模式（FR-002）
- [X] T005 [P] [US1] `frontend/src/components/PlaceDetailDrawer.tsx`——将既有 `⚡ AI 生成` chip（class `ai-gen-chip`）替换为 `<AiGeneratedTag />`、文案对齐「AI 生成整理」；既有 `disclaimer` 段（「AI 生成内容，仅供出行参考……」）保留不动（research.md D4）
- [X] T006 [P] [US1] `frontend/src/components/SourceLeadCard.tsx`——在来源线索卡插入 `<AiGeneratedTag />`

**Checkpoint**: US1 完成——4 处 AI 内容呈现处均带显式标识，可独立核验

---

## Phase 4: User Story 2 - 用户被提示 AI 内容仅供参考、需自行核实 (Priority: P1)

**Goal**: 在首页结果列表区放置一处风险提示，集中呈现、不逐张卡片重复

**Independent Test**: 搜索后，结果列表区顶部能看到一处「仅供参考、请自行核实」风险提示；多张点位卡片时该提示不重复

### Implementation for User Story 2

- [X] T007 [US2] `frontend/src/pages/index/index.tsx`——在结果列表区的两处渲染位置（列表模式 `list-panel` 列表顶部、地图模式 `map-sheet` 列表顶部）各插入一处 `<AiRiskNotice />`；**不**插入条件渲染的 `AnswerPanel`，确保「有点位卡片但 AI 提炼结果区未渲染」时风险提示仍可见（research.md D3 / spec Edge Case）

**Checkpoint**: US2 完成——结果列表区有一处常驻可见的风险提示

---

## Phase 5: User Story 3 - H5 端 AI 内容展示零回归 (Priority: P1)

**Goal**: 确认补标识/提示的改动未破坏 H5 端既有展示

**Independent Test**: `build:h5` 成功；H5 既有内容与布局与改动前一致，仅多出标识/提示

### Implementation for User Story 3

- [X] T008 [US3] 跑 `cd frontend && npm run build:h5`——确认构建成功、无报错
- [X] T009 [US3] H5 浏览器人工核验零回归——AI 提炼结果区 / 点位卡片（紧凑+完整两模式）/ 点位详情 / 来源线索卡 的原有内容、信息层级与布局，除新增标识/提示外与改动前一致；并逐字核对标识文案为「AI 生成整理」（SC-002 / SC-005）

**Checkpoint**: US3 完成——H5 零回归确认

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: 跨端一致性与边界场景验证（对应 FR-004 / SC-004 / SC-006）

- [X] T010 [P] 跑 `cd frontend && npm run build:weapp`——确认构建成功、无报错
- [ ] T011 微信开发者工具人工核验——4 处 AI 内容标识 + 结果区风险提示均可见、与 H5 表现一致；控制台无 WXSS 报错（重点：T002 新增 CSS 未引入 `*` 选择器致编译失败）
- [ ] T012 边界场景核验（H5 + 微信开发者工具）——空状态、网络错误占位、无结果提示处不出现标识与提示；构造「搜索已出点位卡片、但 AI 提炼结果区未渲染」状态，确认风险提示仍可见（per [quickstart.md](./quickstart.md) 第三节）

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 2 Foundational**：无依赖，最先做——BLOCKS US1 与 US2
- **Phase 3 US1** / **Phase 4 US2**：均依赖 Phase 2 完成；二者互不依赖（改不同文件），可并行
- **Phase 5 US3**：依赖 US1 + US2 完成（零回归是对全部改动的验证）
- **Phase 6 Polish**：依赖 US1 + US2 完成

### User Story Dependencies

- **US1（P1）**：Phase 2 后即可开始，不依赖其它故事
- **US2（P1）**：Phase 2 后即可开始，与 US1 改不同文件、完全独立
- **US3（P1）**：验证型故事，需 US1 + US2 的代码改动落地后进行

### Within Each Story

- US1 的 T003–T006 改 4 个不同文件，全部 [P]，可并行
- US2 仅 T007 一个任务

### Parallel Opportunities

- T002 可与 T001 并行（不同文件）
- Phase 2 完成后，US1（T003–T006）与 US2（T007）可全部并行——5 个任务改 5 个不同文件
- T010（build:weapp）可与 T008/T009（H5 验证）并行

---

## Parallel Example: Phase 2 完成后

```text
# US1 的 4 个组件改动 + US2 的 index.tsx 改动，5 个不同文件，可一起推进：
Task T003: AnswerPanel.tsx 插入 AiGeneratedTag
Task T004: PlaceCard.tsx 插入 AiGeneratedTag
Task T005: PlaceDetailDrawer.tsx chip 替换为 AiGeneratedTag
Task T006: SourceLeadCard.tsx 插入 AiGeneratedTag
Task T007: index.tsx 结果列表区插入 AiRiskNotice
```

---

## Implementation Strategy

### MVP（最小可交付）

1. Phase 2 Foundational（T001–T002）——共享组件与样式
2. Phase 3 US1（T003–T006）——显式标识全覆盖
3. **STOP & 核验**：显式标识是合规第一硬要求，US1 完成即一个有意义的增量

### 完整交付（合规要求 US1 + US2 都到位）

1. Phase 2 → US1 → US2 ——显式标识 + 风险提示两项合规均落地
2. Phase 5 US3 ——H5 零回归确认
3. Phase 6 ——双端一致 + 边界场景核验
4. 注：US1（标识）与 US2（风险提示）分别对应不同法规要求，**产品发布前两者都需完成**——US1 单独上线只是增量、不等于合规完成

---

## Notes

- 本功能纯前端、纯 UI 文案，无后端、无数据模型、无平台分文件（research.md D5）
- 合规文案统一在 `AiContentLabels.tsx`——后续若需改文案只改一处
- 「显式标识」与「风险提示」属不同法规要求：标识=《标识办法》+GB 45438-2025；风险提示=《生成式 AI 服务管理暂行办法》
- 流程性合规工作（微信「深度合成」类目声明、用户协议条款、算法备案）不在本任务清单内——见 spec.md「Out of Scope」，由用户侧并行办理
