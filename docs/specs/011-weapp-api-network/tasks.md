---
description: "Task list for 后端 API 网络层适配微信小程序（代码侧）"
---

# Tasks: 后端 API 网络层适配微信小程序（代码侧）

**Input**: Design documents from `/specs/011-weapp-api-network/`

**Prerequisites**: plan.md, spec.md, research.md, quickstart.md

**Tests**: 后端 CORS 改动加 1 条 pytest（项目约定 + US4）；前端无单测设施，靠 `build:h5`/`build:weapp` + 人工核验（plan.md 已说明）。

**Organization**: 按用户故事分组。本 spec 改动面小（6 个文件），各故事可独立验证。

## Format: `[ID] [P?] [Story] Description`

- **[P]**: 可并行（不同文件、无未完成依赖）
- **[Story]**: 所属用户故事（US1/US2/US3/US4）

---

## Phase 1: Setup（验证环境准备）

**Purpose**: 确保后续可验证的环境就绪

- [X] T001 确认验证环境：本地后端可通过 `backend` 目录 venv 起 `uvicorn app.main:app --reload`；微信开发者工具能打开本项目并加载 `frontend/dist/`

---

## Phase 2: Foundational

**本 spec 无阻塞性前置任务** —— 改动是对现有网络层的局部调整，不涉及新建基础设施。各用户故事在 Setup 完成后即可开工。

---

## Phase 3: User Story 1 - 小程序连可配置域名而非 localhost（Priority: P1）🎯 MVP

**Goal**: API 后端地址收敛为单一可配置来源，生产构建未配域名时可察觉，全代码库无写死且不可覆盖的后端地址。

**Independent Test**: 设测试地址 `build:weapp` → 微信开发者工具 Network 面板请求指向该地址、无 `localhost`；不设地址跑 `build:weapp` → 构建日志出现 warn 提示。

### Implementation for User Story 1

- [X] T002 [P] [US1] 删除 `frontend/src/api/client.ts:4` 的硬编码 fallback `|| 'http://127.0.0.1:8000'`，`API_BASE` 只取 `process.env.TARO_APP_API_BASE`（地址唯一来源为 `config/index.js` 注入值，消除两处漂移）
- [X] T003 [P] [US1] 在 `frontend/config/index.js` 的 env 注入处加构建期校验：当 `process.env.TARO_ENV === 'weapp'` 且 `TARO_APP_API_BASE` 仍为 localhost/127.0.0.1 值时，`console.warn` 醒目提示「⚠️ 小程序构建仍指向 localhost，小程序将连不上后端」；不中断构建
- [X] T004 [P] [US1] 修正 `docker-compose.yml:51` 前端容器 `TARO_APP_API_BASE`，从 `http://localhost:8000` 改为 Docker 服务名 `http://api:8000`
- [X] T005 [P] [US1] 在 `.env.example` 的 `CORS_ALLOW_ORIGINS` 一节附近补注释与样例：`TARO_APP_API_BASE` 生产应填已备案的 HTTPS 域名、`CORS_ALLOW_ORIGINS` 生产填 H5 站点域名

**Checkpoint**: US1 完成后，地址来源唯一、可配置、生产构建可察觉。

---

## Phase 4: User Story 2 - AI 搜索在小程序端能返回结果（降级路径）（Priority: P1）

**Goal**: `aiSearchStream` 在小程序端内部自动降级为非流式 `unifiedSearch`，对调用方透明，`index.tsx` 无需改动。

**Independent Test**: 微信开发者工具触发 AI 搜索 → 结果完整返回、控制台无流式相关报错。

⚠️ **依赖**: T006/T007 与 T002 同改 `client.ts`，须在 T002 之后做，避免编辑冲突。

### Implementation for User Story 2

- [X] T006 [US2] 在 `frontend/src/api/client.ts` 的 `aiSearchStream` 开头加平台判断：`process.env.TARO_ENV !== 'h5'` 时不再 `throw`，改为内部 `await unifiedSearch(params.q, params.limit, params.radius_km)`（H5 分支保持原流式逻辑完全不动）
- [X] T007 [US2] 在 `client.ts` 的降级分支实现合成 `complete` 事件：把 `unifiedSearch` 响应组装为与流式 `complete` 一致的数据形状（`answer`/`spots`/`unmapped_candidates`/`warning`/`warning_code`），经 `onEvent` 回调发射；`extract_pending`/`extract_cache_key` 缺省（对照 `frontend/src/pages/index/index.tsx:233-252` 逐字段核对）
- [X] T008 [P] [US2] 更新 `client.ts` 中 `aiSearchStream` 的 JSDoc 注释（`client.ts:79-96`），去掉「小程序端请走 aiSearch」的旧说明，改为说明「小程序端本函数内部自动降级」

**Checkpoint**: US2 完成后，小程序端 AI 搜索可用；`index.tsx` 未被改动。

---

## Phase 5: User Story 3 - H5 端零回归（Priority: P1）

**Goal**: 确认 US1+US2 的改动未破坏 H5 端。

**Independent Test**: `build:h5` 成功；H5 端 AI 搜索仍逐字流式；各业务接口行为与改动前一致。

⚠️ **依赖**: 须在 US1（T002-T005）与 US2（T006-T008）代码改完后执行。

### Implementation for User Story 3

- [ ] T009 [US3] 跑 `cd frontend && npm run build:h5`，浏览器打开 H5：核验 AI 搜索仍为逐字流式效果；点位列表/统一搜索/信源 chip/反馈提交功能正常；控制台无新增报错（对照 quickstart.md 第 1 节）

**Checkpoint**: H5 零回归确认通过。

---

## Phase 6: User Story 4 - 后端允许生产域名跨域访问（Priority: P2）

**Goal**: 把后端 CORS「可配置 + 安全回退」的现有行为锁成回归测试（research.md D4：现有代码已满足 FR-008，无需改后端代码）。

**Independent Test**: `pytest backend/tests/test_cors_config.py` 全过。

⚠️ **独立**: 纯后端，与 US1/US2/US3 无文件冲突，可全程并行。

### Implementation for User Story 4

- [X] T010 [P] [US4] 新增 `backend/tests/test_cors_config.py`：① 设 `CORS_ALLOW_ORIGINS` 为逗号分隔字符串时，origin 正确进入允许白名单；② 设为空时回退到本地默认白名单（`localhost:10086`/`127.0.0.1:10086`），后端不报错——注明「锁住 spec-011 的 FR-008 行为，防回归」

**Checkpoint**: 后端 CORS 行为有测试守护。

---

## Phase 7: Polish & 验收

**Purpose**: 跨故事的整体验收

- [X] T011 [P] 跑全量 `cd backend && pytest`，确认后端无回归
- [ ] T012 按 [quickstart.md](./quickstart.md) 第 2、3 节，设测试地址 `build:weapp` + 微信开发者工具核验：US1（Network 指向所配地址、无 localhost）、US2（AI 搜索降级出结果、无流式报错）
- [X] T013 按 quickstart.md 第 5 节 `grep` 核验 `frontend/src` 下无「不可配置覆盖」的硬编码后端地址（SC-001）

---

## Dependencies & Execution Order

### Phase 依赖

- **Setup (Phase 1)**: 无依赖，立即可做
- **Foundational (Phase 2)**: 空——无阻塞任务
- **US1 (Phase 3)**: Setup 后即可开工
- **US2 (Phase 4)**: 须等 T002 完成（与之同改 `client.ts`）
- **US3 (Phase 5)**: 须等 US1 + US2 代码全部改完
- **US4 (Phase 6)**: 独立，全程可并行
- **Polish (Phase 7)**: 须等 US1/US2/US4 完成

### 关键文件冲突点

- `client.ts` 被 T002、T006、T007、T008 触及 → 这 4 个任务彼此**不可并行**，须按 T002 → T006 → T007 → T008 顺序
- `config/index.js`(T003)、`docker-compose.yml`(T004)、`.env.example`(T005)、`test_cors_config.py`(T010) 各自独立文件

### 并行机会

- T003 / T004 / T005 / T010 可与 T002 同时并行（不同文件）
- US4（T010）可与整个 US1/US2/US3 并行

---

## Parallel Example

```bash
# US1 内部 + US4：4 个不同文件可同时改
Task: "T003 config/index.js 加构建期 warn"
Task: "T004 docker-compose.yml 改服务名"
Task: "T005 .env.example 补注释"
Task: "T010 新增 backend/tests/test_cors_config.py"
# T002 client.ts 也可同时开工，但 T006/T007/T008 必须等它
```

---

## Implementation Strategy

### MVP（US1 + US2）

US1 与 US2 都是 P1，合起来才是「小程序网络层能用」的最小闭环——US1 让小程序连得上地址，US2 让 AI 搜索不报错。建议一起做完再验。

1. Phase 1 Setup
2. Phase 3 US1（T002-T005）
3. Phase 4 US2（T006-T008，T002 之后）
4. Phase 5 US3 H5 零回归核验
5. **STOP 验证**：quickstart.md 第 1-3 节
6. Phase 6 US4 + Phase 7 Polish 收尾

### 增量交付

- US1+US2+US3 → MVP（小程序网络层就绪 + H5 不回归）
- US4 → 后端 CORS 测试守护（可任意时刻并入）

---

## Notes

- 总任务数：13（T001-T013）
- US1: 4 / US2: 3 / US3: 1 / US4: 1 / Setup: 1 / Polish: 3
- `index.tsx` **不在任何任务中被改动**——降级对调用方透明是设计目标，T007 完成后须确认它未被动过
- 前端无单测设施，US1/US2/US3 靠构建 + 人工核验；US4 有 pytest
- 真实世界任务（域名/ICP 备案/HTTPS/微信后台配域名）不在本 tasks，用户并行处理
- 每个任务或逻辑组完成后建议 commit

---

## 实现状态（2026-05-21）

**代码任务全部完成**：T001-T008、T010 已实现。

**自动化验证已通过**：
- `npm run typecheck` 无报错
- `npm run build:h5` 编译成功（仅 1 个无关的 bundle 体积警告）
- `npm run build:weapp` 编译成功；不配域名时 T003 构建期 warn 正确触发、配域名时不触发
- 全量 `pytest` 94 项全过（含新增 `test_cors_config.py` 6 项），后端零回归
- `grep` 核验 `frontend/src` 无写死后端地址（SC-001）
- `index.tsx` 未被改动（降级透明的设计目标达成）

**T009 / T012 待人工 GUI 核验**（自动化部分已做完，剩浏览器 / 微信开发者工具的肉眼检查）：
- T009：build:h5 已成功 + H5 代码路径在编译期不变（`process.env.TARO_ENV` 在 h5 包里被替换为 `'h5'`，新增的非-h5 分支被死代码消除）。剩「浏览器实跑 AI 搜索看逐字流式」需用户按 quickstart §1 做。
- T012：build:weapp 已成功 + 构建期 warn 行为已验。剩「微信开发者工具 Network 面板看请求指向 + AI 搜索降级出结果」需用户按 quickstart §2/§3 做（需启本地后端 + 工具勾「不校验合法域名」）。
