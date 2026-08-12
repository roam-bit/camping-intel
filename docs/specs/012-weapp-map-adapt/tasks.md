---
description: "Task list for 微信小程序地图层适配"
---

# Tasks: 微信小程序地图层适配

**Input**: Design documents from `/specs/012-weapp-map-adapt/`

**Prerequisites**: plan.md, spec.md, research.md, quickstart.md

**Tests**: 前端无单测设施——靠 `build:h5` / `build:weapp` + 微信开发者工具人工核验（plan.md 已说明）。

**Organization**: 按用户故事分组。本 spec 仅动 `frontend/`，核心是新增一个 `MapCanvas.weapp.tsx`。

## Format: `[ID] [P?] [Story] Description`

- **[P]**: 可并行（不同文件、无未完成依赖）
- **[Story]**: 所属用户故事（US1-US5）

---

## Phase 1: Setup（验证环境准备）

- [X] T001 确认验证环境：worktree 根目录 `.env` 已就位（缺则从主仓库 `cp`）；后端本地可起；微信开发者工具能打开 `frontend/dist/`

---

## Phase 2: Foundational（阻塞性前置）

**Purpose**: 建立两端 MapCanvas 共享的类型，是 weapp 地图文件的前提

⚠️ **CRITICAL**: T002 完成前 US1/US2/US3 无法开工（weapp 文件要 import 这个类型）

- [X] T002 抽 `MapCanvasProps` 到新文件 `frontend/src/components/MapCanvas.types.ts`；把 `frontend/src/components/MapCanvas.tsx` 里 `export interface MapCanvasProps {...}` 改为从 `./MapCanvas.types` import（这是本 spec 对 H5 文件的**唯一**改动，纯类型、编译期、零运行时风险）

**Checkpoint**: 共享类型就位，weapp 地图文件可以开建

---

## Phase 3: User Story 1 - 小程序首页地图底图可见（Priority: P1）🎯 MVP

**Goal**: 小程序首页地图区显示一张真实可交互地图，替代当前空白占位。

**Independent Test**: 微信开发者工具打开小程序首页，地图区显示真实地图，可拖动可缩放。

### Implementation for User Story 1

- [X] T003 [US1] 新建 `frontend/src/components/MapCanvas.weapp.tsx`：用 Taro `<Map>` 渲染地图，受控 `longitude`/`latitude`/`scale`，初始 center 取 `userCoord`，开启拖动/缩放；导出与 H5 同名的 `MapCanvas` 组件，props 从 `./MapCanvas.types` 引入（research.md D1）

**Checkpoint**: 小程序首页地图底图可见、可交互

---

## Phase 4: User Story 2 - 点位 marker 显示 + 点击开详情（Priority: P1）

**Goal**: places 点位以 marker 显示在小程序地图上，能看出信源数，点击打开详情。

**Independent Test**: 有点位数据时地图出现对应数量 marker，点 marker 打开详情。

⚠️ **依赖**: T006/T007 与 T003 同改 `MapCanvas.weapp.tsx`，须在 T003 之后顺序做。

### Implementation for User Story 2

- [X] T004 [P] [US2] marker 点位图标资源：在 `frontend/src/assets/` 加一个简单的点位图标 PNG；或决定用 `<map>` 默认 marker 图标——二选一并在文件注释记录决定（research.md D3）
- [X] T005 [US2] `MapCanvas.weapp.tsx` 加 markers：把 `places` 映射成 `<Map>` 的 `markers` 数组——每个含数字 `id`（= places 索引）、经纬度（用 `utils/amap.ts` 的 `toAmapPosition` 转 GCJ-02）、`iconPath`、`callout` 或 `label` 显示信源数（用 `displaySourceCount`）（research.md D3）
- [X] T006 [US2] `MapCanvas.weapp.tsx` 加 `onMarkerTap`：回调拿 `markerId` 反查 `places` 对应项，调 `onMarkerClick(place)`，行为对齐 H5（research.md D5）

**Checkpoint**: 小程序地图上点位可见、可点开详情

---

## Phase 5: User Story 3 - 地图随定位/搜索自动居中（Priority: P1）

**Goal**: 定位成功居中到用户位置；搜索后地图飞到点位范围或搜索中心。

**Independent Test**: 定位后地图中心在用户位置；搜索某地名后视野移到对应区域。

⚠️ **依赖**: 同改 `MapCanvas.weapp.tsx`，须在 T003/T005 之后。

### Implementation for User Story 3

- [X] T007 [US3] `MapCanvas.weapp.tsx` 实现居中：用 state 响应 `places`/`searchCenter`/`locationStatus`/`userCoord`——定位 `ok` → 受控 center 到 `userCoord` + 合理 `scale`；有 `places` → `includePoints` 做 fitView；无点位但有 `searchCenter` → 受控 center 到 `searchCenter`。注意 `includePoints` 与受控 center 二选一驱动、不打架（research.md D4）

**Checkpoint**: 小程序地图居中/缩放随定位与搜索正确变化

---

## Phase 6: User Story 4 - H5 端地图零回归（Priority: P1）

**Goal**: 确认 weapp 地图改动未破坏 H5。

**Independent Test**: `build:h5` 成功；H5 高德地图、marker、控件、fitView、定位、导航 与改动前一致。

⚠️ **依赖**: 在 US1-US3 + US5 代码改完后执行。

### Implementation for User Story 4

- [X] T008 [US4] H5 零回归核验：`cd frontend && npm run build:h5`，浏览器（`localhost:10086`）核验地图/marker/缩放控件/搜索 fitView/定位居中/一键导航 全部正常；`git diff frontend/src/components/MapCanvas.tsx` 确认只有 T002 那一行类型 import 改动（对照 quickstart §1）

**Checkpoint**: H5 地图零回归确认通过

---

## Phase 7: User Story 5 - 小程序「一键导航」可用（Priority: P2）

**Goal**: 小程序端点位详情「一键导航」能唤起导航。

**Independent Test**: 小程序端点「一键导航」唤起微信位置查看页。

⚠️ **独立**: 改 `amap.ts`，与 `MapCanvas.weapp.tsx` 无文件冲突，可与 US1-US3 并行。

### Implementation for User Story 5

- [X] T009 [P] [US5] `frontend/src/utils/amap.ts` 的 `openAmapNavigation` 加 `process.env.TARO_ENV` 分支：weapp 走 `Taro.openLocation`（坐标用 `toAmapPosition` 转 GCJ-02），H5 保持现有 `window.open` 不动（research.md D6）

**Checkpoint**: 小程序端一键导航可用

---

## Phase 8: Polish & 验收

- [ ] T010 `build:weapp` + 微信开发者工具按 [quickstart.md](./quickstart.md) §2-§6 核验：地图显示、marker、居中、**浮层不被地图遮挡**（重点，FR-006）、一键导航
- [X] T011 全量复核 quickstart + 确认 `frontend/src/pages/index/index.tsx` 未被改动（靠 Taro 分平台文件自动选组件，index.tsx 不该动）

---

## Dependencies & Execution Order

### Phase 依赖

- **Setup (P1)**: 无依赖
- **Foundational (P2)**: T002 阻塞 US1/US2/US3
- **US1 (P3)**: T002 后开工
- **US2 (P4)**: T003 后（同文件）
- **US3 (P5)**: T003/T005 后（同文件）
- **US4 (P6)**: US1-US3 + US5 代码改完后
- **US5 (P7)**: 独立，T002 后即可，可与 US1-US3 并行
- **Polish (P8)**: 全部代码完成后

### 关键文件冲突点

- `MapCanvas.weapp.tsx` 被 T003、T005、T006、T007 触及 → 这 4 个任务**不可并行**，须按 T003 → T005 → T006 → T007 顺序
- `MapCanvas.tsx`(T002)、`MapCanvas.types.ts`(T002)、marker 图标(T004)、`amap.ts`(T009) 各自独立

### 并行机会

- T004（marker 图标）、T009（amap.ts 导航）可与 `MapCanvas.weapp.tsx` 的开发并行
- US5（T009）独立于整个 US1-US3

---

## Parallel Example

```bash
# T002 完成后，这几个不同文件可并行：
Task: "T004 加 marker 点位图标 PNG"
Task: "T009 amap.ts openAmapNavigation 加 weapp 分支"
# T003 起 MapCanvas.weapp.tsx 也可同时开工，但 T005/T006/T007 必须排在 T003 后
```

---

## Implementation Strategy

### MVP（US1 + US2 + US3）

三个 P1 故事都在 `MapCanvas.weapp.tsx` 一个文件里逐层叠加——地图显示 → 加点位 → 加居中。合起来才是「小程序地图能用」的最小闭环，建议一起做完再验。

1. Phase 1 Setup → Phase 2 T002（抽类型）
2. Phase 3-5：T003 → T005 → T006 → T007（同文件顺序做）
3. T004、T009 穿插并行
4. Phase 6 US4 H5 零回归核验
5. Phase 8 微信开发者工具核验

### 增量交付

- US1+US2+US3 → 小程序地图 MVP（显示+点位+居中）
- US5 → 一键导航补全（可任意时刻并入）

---

## Notes

- 总任务数：11（T001-T011）
- US1: 1 / US2: 3 / US3: 1 / US4: 1 / US5: 1 / Setup: 1 / Foundational: 1 / Polish: 2
- H5 零回归靠「`MapCanvas.tsx` 几乎不碰」——仅 T002 改一行类型 import；T008 用 git diff 把关
- `index.tsx` 不在任何任务中被改动——靠 Taro 分平台文件约定自动选组件
- 前端无单测，全靠双端构建 + 微信开发者工具人工核验
- 最大风险：原生地图同层渲染（浮层遮挡）——T010 专门核验

---

## 实现状态（2026-05-21）

**代码任务全部完成**：T001-T007、T009 已实现。改动文件：
- 新增 `MapCanvas.weapp.tsx`（weapp 地图）、`MapCanvas.types.ts`（共享类型）、`assets/marker.png`
- 改 `MapCanvas.tsx`（仅抽类型，组件逻辑一字未动）、`amap.ts`（导航加 weapp 分支）、`config/index.js`（copy 配置）

**实现期发现并解决的坑**：marker.png 501 字节会被 webpack 内联成 base64 data URI，而 weapp `<map>` 的 `iconPath` 不认 data URI → 改用 Taro `copy` 配置让 marker.png 作为独立文件进包，`iconPath` 用代码包路径 `/assets/marker.png`。已验构建产物里 `dist/assets/marker.png` 存在、`iconPath` 是路径而非 base64。

**自动化验证已通过**：
- `npm run typecheck` 无报错
- `npm run build:weapp` 编译成功；`marker.png` 作为文件进包；`iconPath` = `/assets/marker.png`
- `npm run build:h5` 编译成功（仅 1 个无关 bundle 体积警告）
- `git diff MapCanvas.tsx` 确认仅类型抽取改动，H5 组件运行逻辑零改动
- `index.tsx` 未被改动

**实现期第二个坑（已修）**：`includePoints` 传空数组 `[]` 会让腾讯地图 SDK 在 `fitBounds` 里读 `undefined.lat` 崩溃（微信开发者工具实测报 `Cannot read property 'lat' of undefined`）。修复：无点位时 `includePoints` 传 `undefined`；并过滤坐标异常的坏点位（FR-009）。重新构建后该崩溃消失（微信开发者工具 Console 已确认）。

**人工 GUI 核验结果（2026-05-22，微信开发者工具 + 浏览器）**：
- ✅ 小程序地图正常显示（腾讯底图），可拖动缩放 —— US1 通过
- ✅ 搜索框 / 地图列表 tab / 筛选栏 / 底部列表面板 等浮层**不被地图遮挡** —— FR-006 通过（同层渲染生效，原计划最大风险点解除）
- ✅ `includePoints` 空数组崩溃已修复 —— Console 不再报 `lat` 错
- ✅ H5 端地图正常渲染（截图核验）；`MapCanvas.tsx` 仅类型抽取改动（git diff 已核）—— US4 零回归
- ✅ `index.tsx` 未被改动 —— T011
- ❌ **未验证：marker 实际渲染（US2）/ 地图随搜索居中（US3）/ 一键导航（US5）** —— 小程序启动时数据加载报 `Error: timeout`（Network 面板证实：根本没发后端请求，卡在更早的启动流程；属独立的小程序数据加载问题，**非本 spec 代码**）→ 取不到点位数据，故 marker / 居中 / 导航 无法肉眼验证。这些功能的代码已写完并通过 typecheck + 构建。

**结论**：spec-012 地图组件代码完成；地图显示与浮层布局已核验；marker/居中/导航 受「小程序数据加载」独立问题阻塞、未能肉眼验证。该数据加载问题建议单独立 spec 处理（线索：app.json 缺定位权限声明）。
