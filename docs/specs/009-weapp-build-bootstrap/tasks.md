---

description: "Task list for spec-009 微信小程序编译跑通 + 平台差异盘点"
---

# Tasks: 微信小程序编译跑通 + 平台差异盘点

**Input**: Design documents from `specs/009-weapp-build-bootstrap/`

**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/差异清单模板.md ✅, quickstart.md ✅

**Tests**: 本 spec 是构建配置 + 盘点，无单元测试可加；验收靠「编译成功」+「微信开发者工具人工核验」。不含 pytest 任务。

**Organization**: 按 user story 分阶段。US1 = 编译产物（MVP）；US2 = 开发者工具跑通；US3 = 差异清单。

## Format: `[ID] [P?] [Story] Description`

- **[P]**: 不同文件、无依赖，可并行
- 所有路径相对 repo root

## Path Conventions

- 前端：`frontend/`
- 文档：`docs/mvp-backlog/`

---

## Phase 1: Setup

**Purpose**: 确认前端工具链就绪

- [X] T001 确认 `frontend/node_modules` 已安装（spec-006 时为产品 frontend 装过 typescript，但完整依赖待确认）；缺则 `cd frontend && npm install --legacy-peer-deps`

---

## Phase 2: Foundational（阻塞前置）

**Purpose**: 微信小程序项目配置 —— 没有它编译产物也打不开

- [X] T002 在 `frontend/` 新建 `project.config.json`：appid=`wxb4776856c0d56676`、projectname、`miniprogramRoot` 指向 weapp 产物目录、compileType=miniprogram、基础 setting（按 data-model.md §实体 1）
- [X] T003 在 `frontend/.gitignore`（或仓库根 .gitignore）加 `project.private.config.json` + `dist/`，避免本地私有配置/产物入库
- [X] T004 检查 `frontend/config/index.js` 的 `mini` 段是否够编译 weapp（postcss 已有；按需补 weapp 编译必要项）

**Checkpoint**: 项目配置就绪，可尝试编译

---

## Phase 3: User Story 1 - Taro 代码编译成微信小程序产物（Priority: P1）🎯 MVP

**Goal**: `build:weapp` 跑通，产物生成

**Independent Test**: `cd frontend && npm run build:weapp` 成功，产物目录生成、无致命错误

### Implementation for User Story 1

- [X] T005 [US1] 跑 `cd frontend && npm run build:weapp`，记录所有编译期报错/警告到临时笔记（后续进差异清单）
- [X] T006 [US1] 逐个修复**阻断构建**的编译错误：只允许「补平台守卫（`process.env.TARO_ENV` 条件分支）」「补 mini/weapp 配置」这类对 H5 透明的改动；非阻断的警告不修、记入清单
- [X] T007 [US1] 重跑 `build:weapp` 确认产物成功生成、构建进程成功结束

**Checkpoint**: 小程序产物能编译出来

---

## Phase 4: User Story 2 - 小程序在微信开发者工具里启动到首页（Priority: P1）

**Goal**: 开发者工具能打开产物，首页非白屏

**Independent Test**: 微信开发者工具导入 `frontend/`，小程序启动，首页可见框架元素（地图空白可接受）

### Implementation for User Story 2

- [X] T008 [US2] 微信开发者工具导入项目（用户操作 / Claude 指导）；若启动白屏，看控制台定位原因
- [X] T009 [US2] 修复**导致首页白屏/崩溃**的运行时错误（FR-004）：优先靠现有 `TARO_ENV` 守卫；漏守卫处补条件分支；地图等组件确保渲染空容器而非抛错。**仅修「阻断首页」级，功能缺失级不修**
- [X] T010 [US2] 确认首页框架元素（搜索框 / 列表区 / 导航栏）可见，地图区域空白/占位但不崩 —— 人工核验 SC-002

**Checkpoint**: 小程序骨架在开发者工具里活着

---

## Phase 5: User Story 3 - 产出平台差异清单（Priority: P1）

**Goal**: 系统盘点所有 H5↔小程序 不兼容点

**Independent Test**: `docs/mvp-backlog/小程序平台差异清单.md` 存在且结构符合 contracts/差异清单模板.md

### Implementation for User Story 3

- [X] T011 [US3] 汇总编译期问题（T005/T006 笔记）+ 运行期问题（T008/T009 开发者工具控制台 + 肉眼观察），创建 `docs/mvp-backlog/小程序平台差异清单.md`，结构严格按 `contracts/差异清单模板.md`
- [X] T012 [US3] 每条差异填全：名称 / 类别 / 现象 / 来源 / 严重度（阻断首页·功能缺失·体验降级）/ 建议归属 spec；MUST 含「小程序↔后端 API 网络层」一项（clarify Q1）
- [X] T013 [US3] 写「按后续 spec 归类汇总」段：确保每个非「已隔离」差异都映射到某后续 spec（地图适配 / 信源外链 / 后端网络层 / 导航 / AI 标注），无悬空

**Checkpoint**: 后续 7.1 spec 的范围输入就绪

---

## Phase 6: Polish & 验证

- [X] T014 跑 `cd frontend && npm run build:h5` 确认 H5 端零回归（SC-004）
- [X] T015 跑后端 `pytest` 确认 88 条不受影响（本 spec 不碰后端，应天然不变——快速确认即可）
- [X] T016 更新 `docs/mvp-backlog/MVP待做清单.md`：7.1 的「编译跑通」勾掉，记 spec-009 完成；更新 memory current_progress.md

---

## Dependencies & Execution Order

- **Phase 1**：无依赖
- **Phase 2**：依赖 Phase 1；T002→T003→T004（配置文件相关，顺序）
- **Phase 3（US1）**：依赖 Phase 2；T005→T006→T007（编译-修-重编译，强顺序）
- **Phase 4（US2）**：依赖 US1（要先有产物）；T008→T009→T010
- **Phase 5（US3）**：依赖 US1+US2（盘点要编译期 + 运行期两方数据）；T011→T012→T013
- **Phase 6**：依赖前面所有

### 关键依赖链

- US3（差异清单）必须在 US1+US2 之后——它汇总的是编译期和运行期实测出的问题，不能凭空写
- T008（开发者工具导入）需要**微信开发者工具已安装** + AppID —— 若工具没装，US2 卡住，需用户先装

### Parallel Opportunities

- 本 spec 大部分任务强顺序（编译→修→重编译→盘点），并行空间小
- T014 / T015（H5 回归 + 后端 pytest）可并行

---

## Implementation Strategy

### MVP First（US1）

1. Phase 1 + 2（配置）
2. Phase 3（US1）—— 产物编译出来

### 增量交付

1. Setup + 配置 → project.config.json 就位
2. US1 → 编译产物（核心）
3. US2 → 开发者工具跑通（要微信开发者工具）
4. US3 → 差异清单（后续 spec 的输入）
5. Polish → H5 回归 + memory 更新

### 风险点

- **微信开发者工具未安装** → US2（T008-T010）做不了。这是开发者本地环境前置——实施到 US2 时若没装需停下来等用户
- 编译期可能遇到只支持浏览器的 npm 依赖 → 记清单，不在本 spec 强行替换
- 现有 `TARO_ENV` 守卫已较完善（research D2），编译/运行跑通风险中等偏低

---

## Notes

- 每完成一个 Phase 提交一次（pre-commit 会跑 ruff/tsc/pytest——本 spec 主要动前端配置，tsc 检查要过）
- US2 涉及 GUI 操作（微信开发者工具），Claude 无法代核验白屏——需用户看屏幕确认
- 严守边界：只编译跑通 + 盘点，不修地图/外链/网络层/导航/标注
