# Implementation Plan: 微信小程序编译跑通 + 平台差异盘点

**Branch**: `009-weapp-build-bootstrap` | **Date**: 2026-05-21 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/009-weapp-build-bootstrap/spec.md`

## Summary

让现有 Taro 前端能编译成微信小程序产物、在微信开发者工具里启动到首页（非白屏），并产出一份系统的「平台差异清单」作为 7.1 后续 spec 的输入。本 spec **只做编译跑通 + 骨架立起来 + 盘点**——地图、信源外链、后端网络层等差异**只记不修**。

**核心改动域**：新建 `frontend/project.config.json`（接入 AppID）；按需微调 `frontend/config/index.js` 的 `mini` 段；修少量阻断 `build:weapp` 的编译错误（若有）；产出 `docs/mvp-backlog/小程序平台差异清单.md`。**不碰后端、不碰业务逻辑、不修地图/外链。**

## Technical Context

**Language/Version**: TypeScript + React 18 + Taro 4（既有前端）

**Primary Dependencies**: 既有 Taro 工具链（`@tarojs/cli`、webpack5 compiler）。无新依赖。

**Storage**: 不涉及（纯前端构建配置）

**Testing**: 编译验证（`build:weapp` / `build:h5` 成功）+ 微信开发者工具人工核验（首页非白屏）；后端 88 条 pytest 不受影响（本 spec 不碰后端）

**Target Platform**: 微信小程序（新增目标）+ H5（既有，不能回归）

**Project Type**: Taro 多端前端

**Performance Goals**: 不适用（bootstrap spec，不追性能）

**Constraints**:
- H5 端零回归（FR-006）—— 所有改动须 H5/小程序双目标兼容
- 不引入新框架/新依赖
- 不修地图、信源外链、后端网络层（只盘点）
- 微信小程序主包 ≤ 2MB（若超限记入清单，分包留后续）

**Scale/Scope**: 单页应用（`pages/index/index`），改动集中在构建配置 + 1 份盘点文档

## Constitution Check

`.specify/memory/constitution.md` 空模板，默认通过。沿用 CLAUDE.md 5 条协作规则。

**Phase 0 / Phase 1 后复查**：✅ 通过（无新依赖、无新服务、纯前端构建配置 + 文档）。

## Project Structure

### Documentation (this feature)

```text
specs/009-weapp-build-bootstrap/
├── plan.md / research.md / data-model.md / quickstart.md
├── contracts/差异清单模板.md
└── tasks.md（/speckit-tasks 阶段生成）
```

### Source Code (repository root)

```text
frontend/
├── project.config.json        # 🆕 微信小程序项目配置（AppID wxb4776856c0d56676）
├── project.private.config.json # 🆕（可选，本地私有配置，应进 .gitignore）
├── config/index.js            # ⚙️ 按需微调 mini 段（确保 weapp 编译参数齐全）
├── src/
│   ├── app.config.ts          # ⚙️ 按需（小程序页面注册 / window 配置兼容性）
│   └── （业务代码）            # ⚙️ 仅修阻断 build:weapp 的编译错误，不改功能
└── （dist/weapp 产物，gitignore）

docs/mvp-backlog/
└── 小程序平台差异清单.md       # 🆕 本 spec 核心交付物之一
```

**Structure Decision**: 沿用既有 Taro 单体前端。`project.config.json` 是微信小程序标准项目文件，放 `frontend/` 根。盘点清单放 `docs/mvp-backlog/`（与 MVP 待做清单等同目录）。后续 7.1 的地图/外链/网络层 spec 各自独立，本 spec 只产出它们的输入清单。

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| —         | —          | —                                   |
