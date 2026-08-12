# Implementation Plan: 后端 API 网络层适配微信小程序（代码侧）

**Branch**: `011-weapp-api-network` | **Date**: 2026-05-21 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/011-weapp-api-network/spec.md`

## Summary

让前端网络层在保持 H5 零回归的前提下具备「连微信小程序」能力。三件事：(1) API 后端地址改为单一可配置来源、生产构建未配域名时可察觉；(2) AI 搜索的流式接口 `aiSearchStream` 在小程序端内部自动降级为非流式 `unifiedSearch`，对调用方透明；(3) 后端 CORS 白名单支持配生产域名。真实世界任务（域名/备案/HTTPS/微信后台）不在范围内。

## Technical Context

**Language/Version**: 前端 TypeScript（Taro 4 + React 18）；后端 Python 3.x（FastAPI）

**Primary Dependencies**: `@tarojs/taro`（含 `Taro.request` / `Taro.getEnv`）、FastAPI `CORSMiddleware`

**Storage**: N/A（本 spec 不碰数据库）

**Testing**: 后端 `pytest`（`backend/tests/`）；前端无单测，靠 `build:h5` / `build:weapp` + 人工核验

**Target Platform**: H5（浏览器）+ 微信小程序（weapp）双端，同一份 Taro 源码编译

**Project Type**: Web 应用（frontend + backend 双目录）

**Performance Goals**: N/A（网络层适配，无性能目标）

**Constraints**: H5 零回归是硬约束；小程序禁 `localhost`/IP、无 `fetch`/`ReadableStream`

**Scale/Scope**: 改动面小——前端 2 文件 + 后端 1 文件 + docker-compose + .env.example，约 5 处

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

项目 `.specify/memory/constitution.md` 仍是未填充的模板（占位符未替换），无可执行的具体条款 → **本 spec 无 constitution 门禁需校验**。

改以项目 `CLAUDE.md`「开发工作流 4 件套」作为事实约束：
- ✅ 已走 spec 流程（specify → plan）
- ✅ 验证阶段：后端 CORS 改动加 1 条 happy-path pytest；前端纯靠双端构建 + 人工核验（无单测设施）
- ✅ 零回归：H5 端为硬约束，US3 专门覆盖

无违规，无需填 Complexity Tracking。

## Project Structure

### Documentation (this feature)

```text
specs/011-weapp-api-network/
├── plan.md              # 本文件
├── spec.md              # 功能规格
├── research.md          # Phase 0 输出——技术选型决策
├── quickstart.md        # Phase 1 输出——验证步骤清单
└── checklists/
    └── requirements.md  # spec 质量检查（已过）
```

无 `data-model.md`：本 spec 不引入数据实体（spec 中「Key Entities」均为配置/运行时概念，非持久化数据）。
无 `contracts/`：不新增/不修改后端 API 接口契约——降级路径复用已存在的 `POST /api/v1/search`。

### Source Code (repository root)

```text
frontend/
├── config/
│   └── index.js                 # [改] env.TARO_APP_API_BASE 默认值策略
├── src/
│   ├── api/
│   │   └── client.ts            # [改] API_BASE 来源；aiSearchStream 内部平台降级
│   └── pages/
│       └── index/index.tsx      # [不改] 调用方——降级对它透明，验证其无需改动

backend/
├── app/
│   └── main.py                  # [不改或微调] CORS——已支持 settings.cors_allow_origins
└── tests/
    └── test_cors_config.py      # [新增] CORS 配置 happy-path 回归测试

docker-compose.yml               # [改] frontend 容器 TARO_APP_API_BASE: localhost → 服务名
.env.example                     # [改] 补生产域名相关变量样例与注释
```

**Structure Decision**: 沿用现有 frontend/backend 双目录结构，无新增目录。改动集中在网络层入口文件，不扩散到业务页面。

## 实现方案（Phase 2 预览，细节留给 /speckit-tasks）

### 1. API 地址可配置化（US1 / FR-001~003）

现状：`client.ts:4` 与 `config/index.js:44` 各写了一份 fallback `http://127.0.0.1:8000`。

做法：
- 地址唯一来源仍是编译期注入的 `process.env.TARO_APP_API_BASE`（Taro 机制：构建时把环境变量「焊死」进产物，类似把配方提前印在包装上）。
- `config/index.js` 的 `envValue` 默认值保留 `http://127.0.0.1:8000` 仅作**本地开发**兜底。
- `client.ts:4` 的 `|| 'http://127.0.0.1:8000'` 字面量删除——地址只认 `config` 注入的值，消除「两处各写一份」的漂移风险。
- **生产构建可察觉**（FR-003）：在 `config/index.js` 加判断——当 `TARO_ENV === 'weapp'` 或显式生产标志下，若 `TARO_APP_API_BASE` 仍是 localhost 值，构建时 `console.warn` 醒目提示「⚠️ 小程序构建仍指向 localhost，小程序将无法连后端」。不硬失败（避免挡住开发者用工具调试），但必须可见。

### 2. AI 搜索流式降级（US2 / FR-004~007）

现状：`aiSearchStream`（`client.ts:97`）在 `typeof fetch === 'undefined'` 时直接 `throw`；`index.tsx:261` 的 catch 才回退到 `unifiedSearch`。

问题：靠 `throw` + catch 触发降级，是「报错驱动」，依赖调用方写对 catch，不够干净。

做法（让降级在网络层内部消化，对调用方透明）：
- 在 `aiSearchStream` 开头做平台判断——用 `process.env.TARO_ENV`（Taro 编译期注入的环境标识，值为 `'h5'` / `'weapp'`）。代码库已有 3 处（`place-helpers.ts:264`、`MapCanvas.tsx:39/75`）统一用此写法，本 spec 沿用，不引入第二种判断方式。
- 非 H5（`TARO_ENV !== 'h5'`）时，**不 throw**，改为内部 `await unifiedSearch(...)`，拿到结果后用同一个 `onEvent` 回调**合成发射**一个 `complete` 事件（数据结构与流式 `complete` 对齐：`answer` / `spots` / `unmapped_candidates` / `warning` 等）。
- 调用方 `index.tsx:192` 的 `onEvent` 处理逻辑天然能接住合成的 `complete` 事件——无需改 `index.tsx`（FR-006）。
- 判断写成「仅 `=== 'h5'` 才走流式，其余一律走非流式」——天然满足「不确定时安全降级」（FR-007）。
- H5 路径完全不动——`TARO_ENV === 'h5'` 时走原流式逻辑（FR-005，零回归）。
- `index.tsx:261` 原有的 catch→unifiedSearch 兜底**保留**，作为「流式真失败」的二层保险。

> 平台判断为何用 `process.env.TARO_ENV` 而非运行时的 `typeof fetch`：`TARO_ENV` 是 Taro 编译时就「焊死」进 H5 包 / 小程序包各自产物的标识——好比出厂时就贴在包装上的产地标签，不会因运行环境波动而误判；`typeof fetch` 是运行时探测，某些基础库场景不稳。且代码库已统一用前者。

### 3. 后端 CORS（US4 / FR-008）

现状：`main.py:31` 已读 `settings.cors_allow_origins`，未配时回退本地白名单；`config.py:11` 的 `_split_cors_origins` validator 已处理「逗号分隔字符串 → list」且跳过空项，空字符串 → `[]` → `main.py` 回退本地默认——**FR-008 现有代码已满足**。

做法：
- **无需改后端代码**——`main.py` + `config.py` 现状即满足 FR-008（已核验）。
- 加 `backend/tests/test_cors_config.py`：把这个「已成立」的行为锁成回归测试——配了 `CORS_ALLOW_ORIGINS` 时 origin 进白名单；空值时回退本地默认。防止未来有人改坏。

### 4. docker-compose 修正（FR-002）

`docker-compose.yml:51` 前端容器 `TARO_APP_API_BASE: http://localhost:8000` —— 容器内 `localhost` 指容器自己，连不到 `api` 服务。改为服务名 `http://api:8000`（Docker Compose 内置服务发现，服务名即主机名）。

### 5. .env.example 补样例（FR-010）

补充生产相关注释：`TARO_APP_API_BASE` 生产应填已备案的 HTTPS 域名；`CORS_ALLOW_ORIGINS` 生产填 H5 站点域名。

## 验证策略

| 验收 | 手段 |
|---|---|
| H5 零回归（US3） | `build:h5` 成功 + 浏览器人工核验：AI 搜索仍逐字流式、各接口正常 |
| 小程序连可配域名（US1） | 设测试域名 `build:weapp` + 微信开发者工具 Network 面板核验 |
| 小程序 AI 搜索降级（US2） | 微信开发者工具触发搜索，结果完整返回、控制台无流式报错 |
| 后端 CORS（US4） | `pytest backend/tests/test_cors_config.py` |
| 全库无写死地址（SC-001） | `grep` 核验 |

## 风险

| 风险 | 说明 | 缓解 |
|---|---|---|
| 合成 `complete` 事件字段对不齐 | 降级路径用 `unifiedSearch` 的响应拼 `complete`，字段若与流式 `complete` 不一致会导致小程序端渲染缺数据 | 对照 `index.tsx:233-252` 的 `complete` 消费逻辑逐字段核对；以 `unifiedSearch` 已有响应结构为准 |
| 微信开发者工具「合法域名」校验 | 测试域名未在小程序后台白名单会被拦 | 验证时勾选「不校验合法域名」（已在 spec assumptions 注明） |
