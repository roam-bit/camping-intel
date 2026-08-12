# Implementation Plan: 微信小程序地图层适配

**Branch**: `012-weapp-map-adapt` | **Date**: 2026-05-21 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/012-weapp-map-adapt/spec.md`

## Summary

让微信小程序端首页显示真实地图——用微信原生 `<map>` 组件（Taro `<Map>`，腾讯底图）。核心做法：**新增一个 weapp 专属的 MapCanvas 文件，H5 的高德 MapCanvas 文件完全不动**，靠 Taro 的多端文件约定（`.weapp.tsx`）让两端各编译各的。weapp 版用声明式 `<Map>` + `markers` 数组渲染点位、`onMarkerTap` 接点击、受控 `longitude/latitude/scale` + `includePoints` 实现居中与 fitView。附带把「一键导航」在小程序端改用 `Taro.openLocation`。H5 零回归靠「文件不碰」从根上保证。

## Technical Context

**Language/Version**: 前端 TypeScript（Taro 4 + React 18）

**Primary Dependencies**: `@tarojs/components` 的 `<Map>`（封装微信原生 `<map>`）、`@tarojs/taro`（`Taro.openLocation` / `Taro.getEnv`）；H5 端沿用高德 JS API（不变）

**Storage**: N/A（纯前端 UI，不碰数据库）

**Testing**: 前端无单测设施——靠 `build:h5` / `build:weapp` + 微信开发者工具人工核验

**Target Platform**: H5（浏览器）+ 微信小程序（weapp）双端，同一份 Taro 源码编译

**Project Type**: Web 应用（frontend + backend 双目录；本 spec 仅动 frontend）

**Performance Goals**: 搜索结果点位量级约 10-15 个，marker 渲染无性能压力；不需要 marker 聚合

**Constraints**: H5 零回归是硬约束；微信原生 `<map>` 是原生组件，层级问题须靠同层渲染解决；坐标须用 GCJ-02

**Scale/Scope**: 改动面小——前端新增 2 文件（`MapCanvas.weapp.tsx` + 共享 props 类型文件）、改 1 个 util（`amap.ts` 加 weapp 导航分支）、可能加 1 个 marker 图标资源；H5 的 `MapCanvas.tsx` 不动

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

项目 `.specify/memory/constitution.md` 仍是未填充模板（占位符未替换），无可执行条款 → **本 spec 无 constitution 门禁需校验**。

改以项目 `CLAUDE.md`「开发工作流 4 件套」作为事实约束：
- ✅ 已走 spec 流程（specify → plan）
- ✅ 验证阶段：前端纯 UI/地图改动，无单测设施 → 靠双端构建 + 微信开发者工具人工核验（与 spec-009/010 一致）
- ✅ 零回归：H5 为硬约束，US4 专门覆盖；本计划用「H5 文件不碰」从结构上保证

无违规，无需填 Complexity Tracking。

## Project Structure

### Documentation (this feature)

```text
specs/012-weapp-map-adapt/
├── plan.md              # 本文件
├── research.md          # Phase 0 输出——技术决策
├── quickstart.md        # Phase 1 输出——验证清单
├── checklists/
│   └── requirements.md  # spec 质量检查
├── spec.md              # 功能规格
└── tasks.md             # /speckit-tasks 输出（本命令不产）
```

无 `data-model.md` / `contracts/`：本 spec 是纯前端 UI 组件适配，不引入新数据实体、不暴露对外接口契约。

### Source Code (repository root)

```text
frontend/src/
├── components/
│   ├── MapCanvas.tsx          # 现有——H5 高德地图；本 spec【不改动】
│   ├── MapCanvas.weapp.tsx    # 【新增】weapp 端原生 <Map> 地图
│   └── MapCanvas.types.ts     # 【新增】两端共享的 MapCanvasProps 类型
├── utils/
│   ├── amap.ts                # 【改】openAmapNavigation 加 weapp 分支（Taro.openLocation）
│   └── coords.ts              # 现有 wgs84ToGcj02——直接复用，不改
├── assets/                    # 可能【新增】一个 marker 点位图标 PNG
└── pages/index/index.tsx      # 【不改】——靠 Taro 多端文件约定自动选对组件
```

**Structure Decision**：Web 应用双目录，本 spec 仅动 `frontend/`。关键结构决策——**用 Taro 多端文件约定拆分 MapCanvas**：weapp 构建自动选 `MapCanvas.weapp.tsx`、H5 构建自动选 `MapCanvas.tsx`。这样 H5 文件「碰都不碰」，零回归从根上成立。详见 research.md D1。

## 关键技术决策（详见 research.md）

| 编号 | 决策 |
|---|---|
| D1 | MapCanvas 双端拆文件：新增 `MapCanvas.weapp.tsx`，H5 的 `MapCanvas.tsx` 不动；`MapCanvasProps` 抽到 `MapCanvas.types.ts` 共享 |
| D2 | 原生组件层级：依赖现代基础库的 `<map>` 同层渲染，首页浮层保持普通 View；微信开发者工具核验确认不被遮挡 |
| D3 | marker 信源数：用 `<map>` marker 的 `callout`/`label` 显示信源数文字 + `iconPath` 点位图标 |
| D4 | 居中/fitView：受控 `longitude`/`latitude`/`scale` 做定位与无点位居中；`includePoints` 做有点位时的 fitView |
| D5 | marker 点击：marker 带数字 `id`（索引回 places），`onMarkerTap` 拿 id 反查 place → 触发 `onMarkerClick` |
| D6 | 一键导航：`amap.ts` 的 `openAmapNavigation` 加 `TARO_ENV` 分支，weapp 走 `Taro.openLocation` |
| D7 | 坐标：复用现有 `wgs84ToGcj02`——高德/腾讯均用 GCJ-02，无需改 |

## Phase 进度

- [x] Phase 0：research.md——7 项技术决策已定，无 NEEDS CLARIFICATION
- [x] Phase 1：quickstart.md（验证清单）；data-model/contracts 经评估不需要
- [ ] Phase 2：tasks.md（由 `/speckit-tasks` 生成）
