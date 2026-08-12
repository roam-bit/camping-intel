# Research: AI 生成内容应用内合规标识

**Feature**: 015-ai-content-label | **Date**: 2026-05-22

本功能技术栈与边界已知（纯前端 Taro 文案补充），无 NEEDS CLARIFICATION。本文件记录关键技术决策。

---

## D1 — 合规文案收敛到单一共享组件

**Decision**：新增 `frontend/src/components/AiContentLabels.tsx`，导出两个小组件：
- `AiGeneratedTag`——显式标识，渲染文案「AI 生成整理」
- `AiRiskNotice`——风险提示，渲染「内容仅供参考，请出行前自行核实」之意

4 个 AI 内容组件 + `index.tsx` 引用这两个组件，**不各自硬编码文案**。

**Rationale**：标识/提示文案是法规敏感内容（国标硬性要求文案含「AI」+「生成/合成」字样）。若 4 处各写一遍，将来改文案要改 4 处、容易漏改导致文案漂移、某处不合规。单一来源 = 改一处即全站生效、不会漂移。

**Alternatives considered**：每处内联写文案——否决，文案漂移风险 + 合规内容无单一可信源。

---

## D2 — 显式标识逐处呈现（4 个共享组件各插一处）

**Decision**：`AiGeneratedTag` 插入 `AnswerPanel` / `PlaceCard` / `PlaceDetailDrawer` / `SourceLeadCard`。PlaceCard 是紧凑与完整两种模式共用的同一组件，插一处即两模式都覆盖。

**Rationale**：合规要求显式标识出现在「每处 AI 内容旁」，不能只放一句全局声明（见合规研究）。这 4 个组件就是产品展示 AI 生成内容的全部位置。卡片级统一标注一处即覆盖该卡片内全部 AI 字段，无需逐字段标。

**Alternatives considered**：只在页面放一句总声明——否决，不符合「内容旁标识」的监管口径。

---

## D3 — 风险提示集中一次，挂结果列表容器

**Decision**：`AiRiskNotice` 放在 `index.tsx` 的结果列表区顶部。列表模式（`list-panel`）与地图模式（`map-sheet`）的列表各放一处。**不挂在 `AnswerPanel` 内**。

**Rationale**：clarify Q2 用户选择「风险提示集中呈现一次、不逐张卡片重复」。但 `AnswerPanel` 是条件渲染（`answer.text` 为空、或 `network_error`/`empty_answer`/`no_traceable_sources` 告警时返回 null）——若提示只挂它，在「搜索已出点位卡片、但 AI 提炼结果区未渲染」时风险提示会缺失。挂在结果列表容器（点位卡片在它内部渲染）→ 只要有 AI 内容展示，提示必可见。列表/地图两模式用户一次只见一个，故对用户是「一次」。

**Alternatives considered**：① 每张卡片都带——用户已否决（重复）。② 只挂 AnswerPanel——有渲染缺口（见上）。③ 页面顶部常驻——用户未选，且与具体结果关联弱。

---

## D4 — PlaceDetailDrawer 既有实现的处理

**Decision**：PlaceDetailDrawer 已有的 `⚡ AI 生成` chip 替换为共享 `AiGeneratedTag`（文案统一为「AI 生成整理」）；已有的 `disclaimer` 段（「AI 生成内容，仅供出行参考……」）**保留不动**。

**Rationale**：详情抽屉是用户主动点开的独立模态视图，自带一段风险话术合理、且已合规。clarify Q2「集中一次、不逐卡片重复」针对的是结果列表区的点位卡片，不波及详情模态——模态自带 disclaimer 不算「逐卡片重复」。chip 换成共享组件是为文案统一（单一来源）。

**Alternatives considered**：删掉详情的 disclaimer 改为不显示——否决，详情视图无风险话术反而是倒退。

---

## D5 — 双端无需平台分文件

**Decision**：新组件与 4 个被改组件均用 Taro `<Text>` / `<View>`，不写 `.weapp.tsx` 变体。

**Rationale**：标识/提示是纯静态文本，Taro 的 `<Text>/<View>` 同一份源码自动编译到 H5 与微信小程序。不像 MapCanvas（spec-012）涉及平台专有的原生 `<map>` 组件需要分文件——本功能无任何平台专有 API。

---

## D6 — 样式复用既有风格 + WXSS 安全

**Decision**：新标识/提示样式加进 `index.css`，复用既有 `ai-gen-chip` 的视觉风格（PlaceDetailDrawer 已在用）。新增选择器须 WXSS 安全。

**Rationale**：复用既有风格 = 视觉一致、用户无割裂感。spec-010 的教训：微信 WXSS 不支持 `*` 通配符选择器，整文件会编译失败 → 新增 CSS 必须用真实标签/类选择器，不用 `*`。标识要小而可辨（符合「显著标识」），但不可压过点位名称等核心信息（FR-006）。

---

## 验证策略

纯 UI 文案改动，前端无单测设施（与 spec-009/010/012 一致）。验证靠：
- `build:h5` + H5 人工核验：4 处标识可见、风险提示一处可见、既有内容零回归
- `build:weapp` + 微信开发者工具人工核验：两端表现一致
- 详见 [quickstart.md](./quickstart.md)
