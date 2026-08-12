# Implementation Plan: 微信小程序样式适配

**Branch**: `010-weapp-style-adapt` | **Date**: 2026-05-21 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/010-weapp-style-adapt/spec.md`

## Summary

spec-009 让小程序编译跑通，但首页主体空白——根因是 H5 的 `vh/vw` 全屏布局在小程序失效（差异清单 R1）。本计划把 `frontend/src/pages/index/index.css` 里 19 处视口单位 + 2 处 `inset` 简写 + ~9 处 `min()` 函数改为微信小程序与 H5 双端都成立的兼容写法，并把求证进度的 `localStorage`（差异清单 R5）抽到双端兼容的 Taro Storage API。技术路线：以「双端通写」为主（不靠 `TARO_ENV` 分叉 CSS），CSS 改成 `100%` 高度链 + `calc()` 拆解 `min()` + 拆分 `inset`；存储层把 `place-helpers.ts` 里两个函数从 `window.localStorage` 换成 `Taro.getStorageSync/setStorageSync`。

## Technical Context

**Language/Version**: TypeScript 5 + React 18，构建框架 Taro 4（多端编译）

**Primary Dependencies**: `@tarojs/taro`（Storage API）、`@tarojs/components`、原生 CSS（无 CSS-in-JS、无 PostCSS 自定义函数）

**Storage**: 求证进度——浏览器 `localStorage` → `Taro.getStorageSync/setStorageSync`（H5 编译为 localStorage、小程序编译为 `wx.getStorageSync`）

**Testing**: 无单元测试（纯样式 + 存储 API 适配）；验证靠 `build:weapp` + 微信开发者工具人工核验 / `build:h5` + H5 人工核验不回归

**Target Platform**: 微信小程序（基础库 ≥ 2.x）+ H5（移动端浏览器）双目标

**Project Type**: 前端单仓（Taro 多端 app），改动集中在 `frontend/`

**Performance Goals**: 不涉及——纯布局/存储改写，无性能目标

**Constraints**: H5 端零回归（硬约束）；不写死像素高度，须自适应机型；扣除小程序导航栏/状态栏占位；不引入 `TARO_ENV` 分叉 CSS（优先双端通写）

**Scale/Scope**: 1 个 CSS 文件（`index.css`，~2080 行，~30 处改点）+ 1 个工具文件（`place-helpers.ts`，2 个函数）；不碰 `app.css`、不碰组件逻辑、不碰后端

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

项目 `.specify/memory/constitution.md` 仍为未填写模板（全是占位符），无可执行的硬性门槛。改用项目 `CLAUDE.md` 的工程约定作为门槛：

- ✅ **SDD 流程**：本 spec 走完整 specify→clarify→plan→tasks→implement
- ✅ **防回归**：US3「H5 零回归」立为独立 P1 user story + FR-006 + SC-004；纯样式无 pytest 可加，符合 CLAUDE.md「纯样式无测试」例外
- ✅ **不碰后端/业务逻辑**：FR-008 明确边界
- ✅ **破坏性操作**：本 spec 无 rm / git push -f 类操作

无违规，无需 Complexity Tracking。

## Project Structure

### Documentation (this feature)

```text
specs/010-weapp-style-adapt/
├── plan.md              # 本文件
├── research.md          # Phase 0：CSS 兼容写法决策
├── data-model.md        # Phase 1：CSS/存储改动清单（本 spec 的「数据」= 改点台账）
├── quickstart.md        # Phase 1：双端验证步骤
├── checklists/
│   └── requirements.md  # spec 自评（已通过）
└── tasks.md             # /speckit-tasks 输出（本命令不创建）
```

### Source Code (repository root)

```text
frontend/
├── src/
│   ├── pages/
│   │   └── index/
│   │       ├── index.css     # ← 主改动：19 vh/vw + 2 inset + ~9 min()
│   │       └── index.tsx     # 不改（仅引用 useViewedSources）
│   ├── utils/
│   │   └── place-helpers.ts  # ← 改动：loadViewedSources / persistViewedSources 换 Taro Storage
│   ├── hooks/
│   │   └── useViewedSources.ts  # 不改（透明受益于 place-helpers 改动）
│   └── app.css               # 不改（已确认无 vh/vw/inset/min）
└── config/index.js           # 不改（spec-009 已配 outputRoot 分目录）
```

**Structure Decision**：Taro 多端单仓。改动只触及 `frontend/src/` 下 2 个文件，CSS 改写靠双端通用语法、存储靠 Taro 跨端 API，因此**无需** `TARO_ENV` 条件分支。`config/index.js` 的 `outputRoot`（spec-009 已按 TARO_ENV 分 `dist/` 与 `dist-h5/`）保证两端构建产物互不覆盖。

## Complexity Tracking

> 无 Constitution 违规，本节空置。
