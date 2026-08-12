# Research: 后端 API 网络层适配微信小程序（代码侧）

**Phase 0 输出** | spec-011 | 2026-05-21

本 spec 无 [NEEDS CLARIFICATION]。以下为方案关键决策的依据，均已在现有代码中核验。

## D1：平台判断方式 —— `process.env.TARO_ENV`

- **Decision**：用 `process.env.TARO_ENV === 'h5'` 区分 H5 与小程序。
- **Rationale**：① 代码库已有 3 处统一用此写法（`place-helpers.ts:264`、`MapCanvas.tsx:39`、`MapCanvas.tsx:75`），沿用即一致；② `TARO_ENV` 是 Taro 编译期注入的常量，H5 包与小程序包各自「焊死」自己的值，不受运行时环境波动影响。
- **Alternatives considered**：
  - `typeof fetch === 'undefined'`（现状写法）—— 运行时探测，不稳；且语义是「有没有 fetch」而非「是不是小程序」，耦合实现细节。
  - `Taro.getEnv()` —— 运行时 API，能用但与代码库现有约定不一致，会引入第二种判断方式。

## D2：降级触发方式 —— 网络层内部消化，不靠 throw

- **Decision**：`aiSearchStream` 在小程序端不再 `throw`，改为内部调用 `unifiedSearch` 并通过 `onEvent` 合成发射 `complete` 事件。
- **Rationale**：现状靠 `throw` + 调用方 `catch` 触发降级（`index.tsx:261`），是「报错驱动降级」——依赖每个调用方都写对 catch，脆弱。把降级收进网络层内部后，调用方对「流式/非流式」无感知，符合 FR-006。
- **Alternatives considered**：
  - 保持 throw、让调用方 catch —— 现状，调用方负担重、易漏。
  - 在 `index.tsx` 里按 `TARO_ENV` 分支调用 `aiSearchStream`/`unifiedSearch` —— 把平台判断泄漏到业务页面，违反 FR-006。

## D3：合成 `complete` 事件的字段对齐

- **Decision**：降级路径拿 `unifiedSearch` 响应后，按流式 `complete` 事件的数据形状组装：`answer` / `spots` / `unmapped_candidates` / `warning` / `warning_code`。
- **Rationale**：调用方 `index.tsx:233-252` 消费 `complete` 时读的就是这些字段。`unifiedSearch` 响应（`client.ts:68`）本就含 `answer`/`spots`/`unmapped_candidates`，字段基本一一对应。
- **注意**：流式 `complete` 还带 `extract_pending` / `extract_cache_key`（后台 extract polling 用）。`unifiedSearch` 是同步返回完整结果、无后台 extract，合成事件中这两个字段应缺省/为空——`index.tsx:246` 已对「无 extract_pending」做了 `else` 分支（仅打 warn 日志，不崩），降级路径走这条分支即可，无需改 `index.tsx`。

## D4：后端 CORS —— 现有代码已满足，只补测试

- **Decision**：不改后端代码，新增 `test_cors_config.py` 锁住现有行为。
- **Rationale**：`config.py:11-16` 的 `_split_cors_origins` validator 已把逗号分隔字符串拆成 list 并跳过空项；`main.py:31` 在 list 为空时回退本地默认白名单。FR-008（可配置 + 安全回退）现状即成立。新增测试是为防回归，符合项目「每修一处加 1 条 pytest」约定。

## D5：生产构建未配域名的「可察觉」方式 —— 构建期 warn，不硬失败

- **Decision**：`config/index.js` 在小程序构建（`TARO_ENV === 'weapp'`）且 `TARO_APP_API_BASE` 仍为 localhost 值时，`console.warn` 醒目提示，但不中断构建。
- **Rationale**：硬失败会挡住「开发者就是想用微信工具连本机后端调试」的合理场景；纯静默又会让人误把连 localhost 的包当生产包（FR-003 要防的正是这个）。warn 是两者平衡——可见、不挡路。
- **Alternatives considered**：构建直接 `throw`/失败 —— 太刚，挡住本地联调。
