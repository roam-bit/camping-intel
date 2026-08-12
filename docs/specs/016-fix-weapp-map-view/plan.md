# Implementation Plan: 修复微信小程序真机地图初始视野不居中

**Branch**: `016-fix-weapp-map-view` | **Date**: 2026-05-23 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/016-fix-weapp-map-view/spec.md`

## Summary

修复真机上微信小程序地图视野不居中到用户定位的 bug。**修复方案不预先拍死**——spec 关键约束要求根因真机实测核实后再定。当前最有把握的方向（社区已知 + 代码佐证）：原生 `<map>` 的声明式 `longitude/latitude` 在挂载后改值不可靠（社区共识「地图只渲染一次」），叠加 `include-points` 挂载时锁视野——所以视野卡在挂载首帧。主选修法：**视野目标变化时让 `<Map>` 重新挂载（React `key` 重挂）**，强制它带正确坐标重新渲染一次；命令式 `MapContext.moveToLocation` 作备选。实现走「改一版 → 用户真机测 → 迭代」循环，真机为唯一验收依据。

## Technical Context

**Language/Version**: 前端 TypeScript（Taro 4 + React 18），仅微信小程序（weapp）端

**Primary Dependencies**: `@tarojs/components` 的 `<Map>`（封装微信原生 `<map>`）；可能用到 `Taro.createMapContext`（命令式备选方案）

**Storage**: N/A（视野渲染 bug，不碰数据）

**Testing**: 无自动化测试——真机调试人工核验。**spec 关键约束：微信开发者工具模拟器表现不作为通过依据**

**Target Platform**: 微信小程序（weapp）；H5 端不动

**Project Type**: Web 应用（frontend + backend；本 spec 仅动 frontend 的 weapp 端）

**Performance Goals**: N/A

**Constraints**: 必须保留 spec-014 崩溃修复（`include-points` 不得退回空数组）；H5 端零回归；根因须真机核实再定方案

**Scale/Scope**: 改动面小——主改 1 个文件 `MapCanvas.weapp.tsx`；可能连带 `index.tsx`（若需调整 `<MapCanvas>` 的渲染条件 / key）

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

项目 `.specify/memory/constitution.md` 仍是未填充模板 → 无 constitution 门禁。

改以 `CLAUDE.md` 4 件套为事实约束：
- ✅ 已走 SDD（specify → clarify → plan）
- ✅ 验证：纯 UI/地图改动、无单测设施 → 真机调试人工核验
- ✅ H5 零回归：靠「不碰 H5 的 `MapCanvas.tsx`」从结构上保证
- ⚠️ 错题本教训（spec-014「凭假设改 `<map>` 反复翻车」）→ 已写进 spec「关键约束」：根因真机核实再动手、真机为验收准绳

无违规，无需 Complexity Tracking。

## Project Structure

### Documentation (this feature)

```text
specs/016-fix-weapp-map-view/
├── plan.md              # 本文件
├── research.md          # Phase 0——根因假设 + 候选修复方案
├── quickstart.md        # Phase 1——真机验证清单
├── checklists/requirements.md
├── spec.md
└── tasks.md             # /speckit-tasks 输出
```

无 `data-model.md` / `contracts/`：本 spec 是地图视野渲染 bug，无数据实体、无对外接口。

### Source Code (repository root)

```text
frontend/src/
├── components/
│   ├── MapCanvas.weapp.tsx   # 【主改】weapp 地图视野控制逻辑
│   └── MapCanvas.tsx         # H5 高德地图——【不碰】，零回归从结构上保证
└── pages/index/index.tsx     # 【可能改】若需调整 <MapCanvas> 的渲染条件 / key
```

无后端改动。

**Structure Decision**：本 spec 仅动 `frontend/` 的 weapp 端。H5 的 `MapCanvas.tsx` 不碰——H5 零回归从根上成立。

## 关键技术决策（详见 research.md）

| 编号 | 决策 |
|---|---|
| D1 | **根因不预先拍死**——实现第一步是真机诊断：确认「include-points 锁视野 + 声明式经纬度挂载后不更新」是不是真因 |
| D2 | **主选方案**：视野目标变化时改 `<Map>` 的 React `key`，强制卸载+重挂——新挂载带正确 `longitude/latitude` 重新渲染一次，绕开「挂载后改值不生效」（社区对「地图只渲染一次」的标准解法）|
| D3 | **备选方案**：命令式 `MapContext.moveToLocation` 移动地图中心。spec-014 已试败命令式 `includePoints`（commit 0aa4225 弃用），不重复该路 |
| D4 | **崩溃护栏保留**：`include-points` 始终非空——重挂时设为目标包围盒，或保留 `CRASH_GUARD_POINTS` 常量 |
| D5 | **真机验收**：实现走「改一版 → 用户真机测 → 迭代」循环；微信开发者工具模拟器不作通过依据。开发者无法自行真机测试，此循环需用户配合 |

## Phase 进度

- [x] Phase 0：research.md——根因假设 + 4 个候选方案已梳理
- [x] Phase 1：quickstart.md（真机验证清单）；data-model / contracts 经评估不需要
- [ ] Phase 2：tasks.md（由 `/speckit-tasks` 生成）
