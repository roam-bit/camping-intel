# Implementation Plan: 修复微信小程序端点位数据加载不出来

**Branch**: `013-fix-weapp-data-load` | **Date**: 2026-05-22 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/013-fix-weapp-data-load/spec.md`

## Summary

修小程序端「打开就是空壳」——点位数据永不加载。核心是**把「加载点位」和「定位是否成功」解耦**：当前 `index.tsx` 只在定位 `ok` 时调 `loadPlaces()`，而小程序定位因缺权限声明必失败 → 永不加载。三处改动：(1) `app.config.ts` 补微信定位权限声明；(2) `index.tsx` 让定位到达任一终态（ok/denied/error）都触发 `loadPlaces()`——失败时用已有的杭州默认坐标兜底；(3) `useUserLocation` 加超时保护，防定位调用挂起导致永远 `pending`、并兜底消除疑似由此引发的 `Error: timeout`。仅前端，H5 零回归。

## Technical Context

**Language/Version**: 前端 TypeScript（Taro 4 + React 18）

**Primary Dependencies**: `@tarojs/taro`（`Taro.getLocation`）；小程序 app 配置（`defineAppConfig`）

**Storage**: N/A（不碰数据库）

**Testing**: 前端无单测设施——靠 `build:h5` / `build:weapp` + 微信开发者工具人工核验

**Target Platform**: H5 + 微信小程序（weapp）双端，同一份 Taro 源码

**Project Type**: Web 应用（frontend + backend；本 spec 仅动 frontend）

**Performance Goals**: N/A（bug 修复）

**Constraints**: H5 零回归（定位成功路径行为不变）；后端不动；定位权限声明须符合微信小程序规范

**Scale/Scope**: 改动面小——3 个前端文件：`app.config.ts`、`pages/index/index.tsx`、`hooks/useUserLocation.ts`

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

项目 `.specify/memory/constitution.md` 仍是未填充模板，无可执行条款 → **本 spec 无 constitution 门禁需校验**。

以项目 `CLAUDE.md`「开发工作流」为事实约束：
- ✅ 已走 spec 流程（specify → plan）
- ✅ 验证：bug 修复，前端无单测设施 → 双端构建 + 微信开发者工具人工核验（与 spec-009/010/012 一致）。CLAUDE.md「每修 bug 加 regression 测试」因前端无单测设施无法执行，已在此记录。
- ✅ 零回归：H5 为硬约束，US5 专门覆盖

无违规，无需填 Complexity Tracking。

## Project Structure

### Documentation (this feature)

```text
specs/013-fix-weapp-data-load/
├── plan.md              # 本文件
├── research.md          # Phase 0——根因与方案决策
├── quickstart.md        # Phase 1——验证清单
├── checklists/requirements.md
├── spec.md
└── tasks.md             # /speckit-tasks 输出
```

无 `data-model.md` / `contracts/`：纯前端 bug 修复，不引入数据实体、不动接口契约。

### Source Code (repository root)

```text
frontend/src/
├── app.config.ts                 # 【改】补微信定位权限声明（permission + requiredPrivateInfos）
├── pages/index/index.tsx         # 【改】定位到达任一终态都触发 loadPlaces（解耦）
├── hooks/
│   ├── useUserLocation.ts        # 【改】加定位超时保护，保证总能到达终态
│   └── usePlaces.ts              # 【不改】loadPlaces 已用传入的 userCoord，无需动
└── components/MapCanvas.*        # 【不改】spec-012 已完成
```

**Structure Decision**：Web 应用双目录，本 spec 仅动 `frontend/` 的 3 个文件。核心改动是「解耦定位与数据加载」（research.md D2），其余两处是配套（权限声明 + 超时保护）。

## 关键技术决策（详见 research.md）

| 编号 | 决策 |
|---|---|
| D1 | `app.config.ts` 补 `permission['scope.userLocation']` + `requiredPrivateInfos: ['getLocation']`——weapp-only，H5 忽略 |
| D2 | `index.tsx` 的定位 useEffect：`ok`/`denied`/`error` 三种终态**都**调 `loadPlaces()`；失败时用 `useUserLocation` 已有的杭州默认坐标。这是修复主体 |
| D3 | `useUserLocation` 给 `Taro.getLocation` 加超时保护（`Promise.race` + N 秒超时）——保证定位总能到达终态、不卡 `pending`，避免调用挂起 |
| D4 | `Error: timeout`（假设，未证实）：疑为 `wx.getLocation` 缺权限声明而挂起 → 微信运行时超时报未捕获错。预期 D1+D3 消除它；实现后微信开发者工具核验确认 |
| D5 | H5 零回归：D1 是 weapp-only 配置 H5 忽略；D2 让 H5 定位成功路径不变、失败时也 loadPlaces（修复非回归）；D3 对 H5 一致生效 |

## Phase 进度

- [x] Phase 0：research.md——5 项决策已定；`Error: timeout` 根因标为假设、待实现期核验
- [x] Phase 1：quickstart.md（验证清单）；data-model/contracts 经评估不需要
- [ ] Phase 2：tasks.md（由 `/speckit-tasks` 生成）
