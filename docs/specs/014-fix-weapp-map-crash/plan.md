# Implementation Plan: 彻查并修复微信小程序地图 marker 渲染崩溃

**Branch**: `014-fix-weapp-map-crash` | **Date**: 2026-05-22 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/014-fix-weapp-map-crash/spec.md`

## Summary

修微信小程序原生 `<map>` 一加载点位就渲染层崩溃（`Cannot read property 'lat' of undefined`，栈 `fitBounds ← pointsChanged`），致 marker 显示不出来。**根因已查证**（research.md）：Taro 4 的 `<Map>` 组件给 `include-points` 硬编码了默认值空数组 `[]`，编译后无论 React 层传不传 `includePoints`，原生 `<map>` 永远收到 `include-points=[]` → 每次渲染触发 `pointsChanged → fitBounds([])` → 崩。这解释了 spec-012/013 在 React 层「传 undefined / 移除 prop」、以及换稳定基础库为何都无效——问题在 Taro 编译层，碰不到。修复（research.md D1/D2）：`MapCanvas.weapp.tsx` 始终给 `includePoints` 喂 ≥2 个有效坐标点（有 marker 用 marker 坐标，不足 2 个用围绕中心的合成点补齐），从源头杜绝空数组；并移除 spec-013 基于错误判断手写的 `viewForMarkers`，视野改由 `include-points` 单一驱动。仅改 1 个前端 weapp 文件，H5 零回归。

## Technical Context

**Language/Version**: 前端 TypeScript（Taro 4 + React 18）

**Primary Dependencies**: `@tarojs/components` 的 `<Map>`（封装微信原生 `<map>` 组件）；`@tarojs/taro`

**Storage**: N/A（不碰数据库、不动接口契约）

**Testing**: 前端无单测设施——靠 `build:weapp` / `build:h5` + 微信开发者工具人工核验（与 spec-009/010/012/013 一致）

**Target Platform**: 微信小程序（weapp）；H5 须零回归

**Project Type**: Web 应用（frontend + backend；本 spec 仅动 frontend 的 weapp 端）

**Performance Goals**: N/A（bug 修复）

**Constraints**: H5 零回归（硬约束，US2）；仅改 frontend weapp 端；修复须建立在已验证根因之上（FR-002——已满足，见 research.md 证据分级）

**Scale/Scope**: 改动面极小——1 个前端文件 `frontend/src/components/MapCanvas.weapp.tsx`

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

项目 `.specify/memory/constitution.md` 仍是未填充模板，无可执行条款 → **本 spec 无 constitution 门禁需校验**。

以项目 `CLAUDE.md`「开发工作流」为事实约束：
- ✅ 已走 spec 流程（specify → plan）。clarify 跳过——spec 无 [NEEDS CLARIFICATION] 标记、根因已在本会话查清，无歧义可澄清。
- ✅ 验证：bug 修复、前端无单测设施 → 双端构建 + 微信开发者工具人工核验。CLAUDE.md「每修 bug 加 regression 测试」因前端无单测设施无法执行，已在此记录（与 spec-009/010/012/013 一致）。
- ✅ 零回归：H5 为硬约束，US2 + research.md D4 从结构上保证（只改 weapp 文件，H5 文件不碰）。

无违规，无需填 Complexity Tracking。

## Project Structure

### Documentation (this feature)

```text
specs/014-fix-weapp-map-crash/
├── plan.md                  # 本文件
├── research.md              # Phase 0——根因（已验证机制 + 证据分级）+ D1-D4 决策
├── quickstart.md            # Phase 1——双端验证清单
├── checklists/requirements.md
├── spec.md
└── tasks.md                 # /speckit-tasks 输出
```

无 `data-model.md` / `contracts/`：纯前端 bug 修复，不引入数据实体、不动接口契约。

### Source Code (repository root)

```text
frontend/src/components/
├── MapCanvas.weapp.tsx      # 【改】唯一改动文件——始终喂非空 includePoints、删 viewForMarkers
├── MapCanvas.tsx            # 【不改】H5 端（高德 JS API），不碰 → H5 零回归
└── MapCanvas.types.ts       # 【不改】两端共享 props 契约
```

**Structure Decision**：Web 应用双目录，本 spec 仅动 `frontend/` 的 1 个 weapp 专属文件。H5 与 weapp 是 Taro 分平台文件（spec-012 D1 拆分），改 weapp 文件结构上不可能波及 H5。

## 关键技术决策（详见 research.md）

| 编号 | 决策 |
|---|---|
| 根因 | Taro `<Map>` 给 `include-points` 硬编码默认值 `[]`，编译后强制注入原生 `<map>` → `fitBounds([])` 崩。机制已验证（读 Taro 源码），因果为强推断、待运行时核验 |
| D1 | `MapCanvas.weapp.tsx` 始终传 `includePoints` 且保证 ≥2 个有效点：有 marker 用 marker 坐标；不足 2 个用围绕中心（搜索中心/用户定位/杭州默认）的合成点补齐——空数组从源头消除 |
| D2 | 删除 spec-013 手写的 `viewForMarkers` 函数 + 受控 `view` state；视野由 `include-points` 单一驱动，避免两套机制打架 |
| D3 | 否决「改 Taro 配置去掉默认值」（脆弱、全局、未验证）与「换地图方案」（FR-003 兜底不触发——原生 `<map>` 可修）|
| D4 | H5 零回归：只改 `MapCanvas.weapp.tsx`，`MapCanvas.tsx` 不碰 |

## Phase 进度

- [x] Phase 0：research.md——根因（已验证机制 + 证据分级）+ D1-D4 决策
- [x] Phase 1：quickstart.md（双端验证清单）；data-model / contracts 经评估不需要
- [ ] Phase 2：tasks.md（由 `/speckit-tasks` 生成）
