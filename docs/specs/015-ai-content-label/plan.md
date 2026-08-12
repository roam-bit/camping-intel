# Implementation Plan: AI 生成内容应用内合规标识

**Branch**: `015-ai-content-label` | **Date**: 2026-05-22 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/015-ai-content-label/spec.md`

## Summary

给产品所有展示 AI 生成内容的界面位置补齐合规标识。核心做法：**新增一个共享组件文件承载合规文案**（`AiContentLabels.tsx`，导出「显式标识」`AiGeneratedTag` 与「风险提示」`AiRiskNotice` 两个小组件），在 4 个 AI 内容组件（AnswerPanel / PlaceCard / PlaceDetailDrawer / SourceLeadCard）逐处插入显式标识「AI 生成整理」，并在首页结果列表区放置一处风险提示。组件均用 Taro `<Text>/<View>`、编译到 H5 与微信小程序两端，无需平台分文件。合规文案集中在一个组件里 = 单一来源、不会漂移。H5 零回归靠「只增不改既有结构」+ 双端构建/人工核验保证。

## Technical Context

**Language/Version**: 前端 TypeScript（Taro 4 + React 18）

**Primary Dependencies**: `@tarojs/components`（`<Text>` / `<View>`）；无新增第三方依赖

**Storage**: N/A（纯前端 UI 文案，不碰数据库、不碰后端）

**Testing**: 前端无单测设施——靠 `build:h5` / `build:weapp` + H5 人工核验 + 微信开发者工具人工核验

**Target Platform**: H5（浏览器）+ 微信小程序（weapp）双端，同一份 Taro 源码编译

**Project Type**: Web 应用（frontend + backend 双目录；本 spec 仅动 frontend）

**Performance Goals**: N/A——纯静态文本元素，无性能影响

**Constraints**: H5 零回归是硬约束；标识文案须含「AI」+「生成」字样（强制性国标 GB 45438-2025）；新增 CSS 须 WXSS 安全（无 `*` 通配符选择器等，遵 spec-010 教训）

**Scale/Scope**: 改动面小——新增 1 个组件文件，改 4 个 AI 内容组件 + `index.tsx` + `index.css`；无后端改动、无数据模型、无平台分文件

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

项目 `.specify/memory/constitution.md` 仍是未填充模板（占位符未替换），无可执行条款 → **本 spec 无 constitution 门禁需校验**。

改以项目 `CLAUDE.md`「开发工作流 4 件套」作为事实约束：

- ✅ 已走 spec 流程（specify → clarify → plan）
- ✅ 验证阶段：纯 UI 文案改动、无单测设施 → 双端构建 + 人工核验（与 spec-009/010/012 一致）
- ✅ 零回归：H5 为硬约束（US3 专门覆盖）；本计划用「只新增标签元素、不改既有结构与逻辑」从结构上保证

无违规，无需填 Complexity Tracking。

## Project Structure

### Documentation (this feature)

```text
specs/015-ai-content-label/
├── plan.md              # 本文件
├── research.md          # Phase 0 输出——技术决策
├── quickstart.md        # Phase 1 输出——验证清单
├── checklists/
│   └── requirements.md  # spec 质量检查
├── spec.md              # 功能规格
└── tasks.md             # /speckit-tasks 输出（本命令不产）
```

无 `data-model.md` / `contracts/`：本 spec 是纯前端 UI 文案补充，不引入新数据实体、不暴露对外接口契约。

### Source Code (repository root)

```text
frontend/src/
├── components/
│   ├── AiContentLabels.tsx     # 【新增】导出 AiGeneratedTag（显式标识「AI 生成整理」）
│   │                           #        + AiRiskNotice（风险提示）——合规文案的单一来源
│   ├── AnswerPanel.tsx         # 【改】AI 提炼结果区——插入 AiGeneratedTag
│   ├── PlaceCard.tsx           # 【改】点位卡片（紧凑 + 完整两模式共用此组件）——插入 AiGeneratedTag
│   ├── PlaceDetailDrawer.tsx   # 【改】点位详情——既有 `⚡ AI 生成` chip 换成 AiGeneratedTag、文案对齐；既有 disclaimer 保留
│   └── SourceLeadCard.tsx      # 【改】来源线索卡——插入 AiGeneratedTag
└── pages/index/
    ├── index.tsx               # 【改】结果列表区（列表模式 list-panel + 地图模式 map-sheet）各放一处 AiRiskNotice
    └── index.css               # 【改】新增标识/提示样式（复用既有 ai-gen-chip 风格，WXSS 安全）
```

无 `backend/` 改动。

**Structure Decision**：Web 应用双目录，本 spec 仅动 `frontend/`。关键结构决策——**合规文案收敛到单一共享组件**：`AiContentLabels.tsx` 是「AI 生成整理」标识文案与风险提示文案的唯一定义处，4 个 AI 内容组件引用它而非各自硬编码。合规文案是法规敏感内容，单一来源避免 4 处文案漂移、将来改文案只改一处。详见 research.md D1。

## 关键技术决策（详见 research.md）

| 编号 | 决策 |
|---|---|
| D1 | 合规文案单一来源：新增 `AiContentLabels.tsx`，导出 `AiGeneratedTag`（显式标识）+ `AiRiskNotice`（风险提示）两个小组件；4 处组件引用之，不各自硬编码文案 |
| D2 | 显式标识逐处呈现：`AiGeneratedTag` 插入 AnswerPanel / PlaceCard / PlaceDetailDrawer / SourceLeadCard 四个共享组件——PlaceCard 一处即覆盖紧凑与完整两模式 |
| D3 | 风险提示集中一次：`AiRiskNotice` 放在 `index.tsx` 结果列表区顶部；列表模式（`list-panel`）与地图模式（`map-sheet`）各一处，用户一次只见一个模式 → 对用户即「一次」。挂在结果列表容器、**不挂条件渲染的 AnswerPanel**（防「有卡片无 AnswerPanel」时提示缺失，见 spec Edge Case） |
| D4 | PlaceDetailDrawer 既有部分实现：已有 `⚡ AI 生成` chip + `disclaimer` 风险话术——本 spec 把 chip 换成共享 `AiGeneratedTag`（文案对齐「AI 生成整理」），既有 disclaimer 保留不动（详情是独立模态视图，自带风险话术合理且不与 Q2「结果列表集中一次」冲突） |
| D5 | 双端无需分文件：4 个组件与新组件均用 Taro `<Text>/<View>`，自动编译到 H5 与 weapp 两端，不需 `.weapp.tsx` 变体 |
| D6 | 样式：复用既有 `ai-gen-chip` 视觉风格，新样式加进 `index.css`，须 WXSS 安全（无 `*` 选择器，遵 spec-010 教训）；标识小而可辨、不压过点位名等核心信息 |

## 实现期重要发现

- **PlaceDetailDrawer 已有部分实现**：点位详情抽屉已存在 `⚡ AI 生成` chip（class `ai-gen-chip`）+ 一段 `disclaimer` 风险话术（「AI 生成内容，仅供出行参考……」）。故本 spec 对它的改动是「替换为共享组件、文案对齐」而非从零新增。spec 的 US1 原表述「所有 AI 内容都没有显式标识」据此已修正为「大多没有、仅详情有一处」。
- AnswerPanel 既有标题为「AI 提炼结果」（含「AI」、缺「生成/合成」字样，不单独达标）——插入 `AiGeneratedTag` 即满足 FR-008，标题文字本身可不改。

## Phase 进度

- [x] Phase 0：research.md——6 项技术决策已定，无 NEEDS CLARIFICATION
- [x] Phase 1：quickstart.md（验证清单）；data-model / contracts 经评估不需要
- [ ] Phase 2：tasks.md（由 `/speckit-tasks` 生成）
