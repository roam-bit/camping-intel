# Feature Specification: 信源发布时间 HTML meta fallback

**Feature Branch**: `007-meta-time-fallback`

**Created**: 2026-05-20

**Status**: Draft

**Input**: User description: "spec-002 解决了「URL 路径含日期」类网站的信源发布时间提取，但对 URL 不含日期的网站（smzdm/知乎专栏/博客）只能 fallback 到 citation/snippet 启发式抽取——实测污染率 100%（错位 22-43 天）。新增一层兜底：抓 HTML 的 og:published_time 等 meta 标签。"

## Clarifications

### Session 2026-05-20

- Q: 回灌跑完后要不要在 DB 标记「已核验」？ → A: 加 `source_time_method` 列（枚举值 url_path / meta_og / meta_article_published / meta_publishdate / citation / snippet）。可观测 + 重复跑安全（脚本只重跑 method='citation'/'snippet' 的行）
- Q: meta 时间和 citation 时间冲突时谁优先？ → A: meta 优先（FR-007 原定顺序：URL → meta → citation → snippet）。自动化元数据比 LLM 启发式可信

### Session 2026-05-21（实施期发现，边界调整）

- 发现：实测 smzdm / 携程 / B站 等站有 JS 反爬，纯 httpx GET 拿不到真实 HTML（返回 HTTP 202 探针页）。原 spec「不引入 Playwright」假设被证伪。
- 决议（C 混合方案）：httpx 先试 → 检测到反爬挑战页（HTTP 202 / probe.js 特征）→ 回退用 Playwright 渲染（复用 spec-006 chromium）。无反爬站仍走 httpx 快路径。
- 进一步发现：headless Playwright 仍被 smzdm 反爬识别拦截（probe.js 检测无头浏览器）。结论：smzdm 等强反爬站服务端抓取不可靠，不投入反爬军备竞赛。
- 止血策略：meta 抓取失败 + 原日期来自 citation/snippet（已知不可靠）→ 把 source_time 置空，前端显示「日期未知」。宁可空、不可错。新增 source_time_method 枚举值 `unverified`。

## User Scenarios & Testing *(mandatory)*

### User Story 1 - 信源发布时间真实可信（Priority: P1）

用户搜索一个露营点（如「深圳坪山免费露营」），AI 返回的信源列表里有一条来自 smzdm 等 URL 不含日期的网站。**用户希望信源卡片显示的发布日期就是原网页的真实发布日期**——而不是 AI 从文章里随手抽到的某个无关日期（评论/相关推荐/活动）。

**Why this priority**：P1 因为这是产品「信源求证」承诺的核心——信源时间错位 30 天意味着用户可能基于"几天前的新信息"做决策，但实际信源是"几个月前的旧帖"；反过来"新鲜内容"被显示成"过期内容"也会让用户错过好结果。比 marker 错位还隐蔽（用户不会主动核对日期）。

**Independent Test**：给定一个真实 smzdm URL（如 `https://post.smzdm.com/p/az8pvqqr/`），调用后端的时间解析服务，5 秒内返回 2026-03-15（与原网页 `<meta property="article:published_time">` 一致，误差 ≤ 1 天）。

**Acceptance Scenarios**:

1. **Given** 一条信源 URL 来自 smzdm.com（URL 路径无日期段），**When** 后端的信源时间解析触发，**Then** 5 秒内返回该网页 `<meta property="article:published_time">` 或 `og:published_time` 标签里的真实日期
2. **Given** 一条信源 URL 来自人民网（URL 路径含日期 `/2024/1108/`），**When** 后端的信源时间解析触发，**Then** 直接用 URL 路径里的日期，**不**触发额外 HTTP 请求（节省带宽和延迟）
3. **Given** 同一个 URL 在 24 小时内被多次搜索命中，**When** 第 2+ 次解析，**Then** 直接从 Redis 缓存返回，单次延迟 ≤ 100ms

---

### User Story 2 - 抓不到 meta 时安全降级（Priority: P1）

如果一个网页**没有** `og:published_time` 等标签（旧博客 / 简陋页面 / 反爬墙拦截 / 超时），系统**不能**抛错让整次搜索失败，也**不能**让 AI 启发式抽取的错日期蒙混过关——应清晰地降级到「日期未知」或回退到 spec-002 原 fallback 链。

**Why this priority**：和 Story 1 同等关键。返回错的日期比返回"日期未知"更糟糕——用户基于错日期可能做错决策。这条是「宁可空、不可错」的护栏。

**Independent Test**：构造 4 个降级场景：(a) HTTP 超时 (b) HTTP 4xx/5xx (c) HTML 有响应但无 meta 标签 (d) HTML 解析出错。每个场景调用都应返回 None 且不抛异常。

**Acceptance Scenarios**:

1. **Given** 一个 URL HTTP GET 超时 > 5 秒，**When** 时间解析触发，**Then** 接口返回 None + 状态 `timeout`，不抛错
2. **Given** 一个 URL 返回 404，**When** 时间解析触发，**Then** 接口返回 None + 状态 `http_error`，不抛错
3. **Given** 一个 URL HTML 里没有任何已知 meta 时间标签，**When** 时间解析触发，**Then** 接口返回 None + 状态 `no_meta`，**回退到 spec-002 原有的 citation/snippet 路径**（不破坏原行为）
4. **Given** HTTP 解析任何异常，**When** 解析触发，**Then** 接口返回 None + 状态 `error`，不抛错

---

### User Story 3 - 历史脏数据回灌修正（Priority: P2）

后端工程师/PM 希望能用一次性脚本扫描 DB 里 232 条「URL 无日期 + 有 source_time」候选源，重新抽 meta 真实日期、UPDATE source_time。**演示阶段抽样 3/3 全部错位** —— 这个脏数据已经在 DB 里，不修就一直影响。

**Why this priority**：P2 因为不阻塞新搜索（spec-007 上线后新搜的数据自动准），但**老数据**用户一搜还能看到错日期。回灌脚本能让现存数据集"一次性变干净"。

**Independent Test**：跑一次性脚本，预期：
- 扫描 232 条候选
- ≥ 80% 能成功抽到 meta 时间（smzdm 是大头 42 条，几乎全部有 og 标签）
- UPDATE 后再抽样 10 条与原网页对比，准确率 ≥ 95%
- 失败的（无 meta / 反爬 / 超时）保留原 source_time，不删数据

**Acceptance Scenarios**:

1. **Given** DB 里 232 条候选记录，**When** 跑一次性脚本，**Then** 10 分钟内跑完，结构化日志显示成功 / 失败 / 跳过 三类计数
2. **Given** 脚本完成后再抽样 10 条 smzdm URL，**When** 与原网页 `<meta>` 对比，**Then** 准确率 ≥ 95%

---

### User Story 4 - 性能可观测（Priority: P3）

后端工程师希望能从结构化日志看每次 meta_time 解析的 (url / duration_ms / status / cache_hit / source_tag) 字段，便于：(a) 发现某域名频繁 timeout 时调整选择策略 (b) 评估缓存命中率是否健康 (c) 上线后监控引入此 fallback 是否对整体搜索延迟有不可接受的影响。

**Why this priority**：P3 可观测性是质量底座，但不直接影响用户。

**Independent Test**：跑一次包含 smzdm 信源的搜索，看后端 stdout 有 `meta_time.resolved` 日志，含 5 个字段。

**Acceptance Scenarios**:

1. **Given** 一次搜索触发 N 次 meta 时间解析，**When** 搜索完成，**Then** 后端日志可见 N 行结构化日志，每行至少含 `url, duration_ms, status (matched/timeout/http_error/no_meta/error), cache_hit, source_tag (og/article/publishdate/...)`

---

### Edge Cases

- meta 里的日期格式异构（ISO 8601 / RFC 2822 / 中文 "2026年3月15日" / 时间戳）：用宽松解析，识别失败归为 `no_meta`
- meta 时间是未来时间（如 2099-01-01 hallucination 防护）：拒绝接受，回到原 fallback 链
- meta 时间是远古时间（< 2010）：拒绝接受（露营/驻车产品的有效信源时间窗内不会有 2010 之前的）
- HTML 体积巨大（> 5MB）：只读前 256KB（meta 标签一般在 `<head>` 内），避免内存爆炸
- 同一域名连续多个 URL 抓取：进程级 semaphore ≤ 5（复用 spec-006 模式），避免被目标站误判 DDoS

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: 系统 MUST 提供一个统一入口 `resolve_meta_published_at(url) -> datetime | None`，当 URL 路径不含日期时被 `resolve_published_at` 调用作为优先于 citation 的兜底
- **FR-002**: 系统 MUST 从 HTTP GET 返回的 HTML 中按优先级抽取以下 meta 标签的内容：
  1. `<meta property="og:published_time" content="...">`
  2. `<meta property="article:published_time" content="...">`
  3. `<meta name="publishdate" content="...">`（中文站常见）
  4. `<meta name="pubdate" content="...">`
  5. `<meta itemprop="datePublished" content="...">`
- **FR-003**: 系统 MUST 单次 HTTP GET 超时设为 5 秒；超时返回 None + 状态 `timeout`，不抛错
- **FR-004**: 系统 MUST 对 HTTP 4xx/5xx 状态码返回 None + 状态 `http_error`，不抛错
- **FR-005**: 系统 MUST 缓存解析结果到 Redis 24h（key 命名空间 `meta_time:v1:`，key 由 URL 哈希）；命中缓存跳过 HTTP，单次 ≤ 100ms
- **FR-006**: 系统 MUST 拒绝接受超出 [2010-01-01, 当前时间 + 1 天] 范围的 meta 时间（防 hallucination / CMS bug）
- **FR-007**: 系统 MUST 在 `resolve_published_at` 中插入新 fallback 层（顺序: URL 路径 → **meta**（新增）→ citation → snippet），保持原 fallback 链向下兼容
- **FR-008**: 系统 MUST 在 URL 路径含日期时**不**调用 meta 解析（节省 HTTP 请求，FR-007 优先级保证）
- **FR-009**: 系统 MUST 提供一次性脚本 `scripts/backfill_meta_time.py`：扫描 `sources` 表里 URL 路径无日期 + source_time 非空的候选行，重新解析 meta 并 UPDATE source_time；失败/无 meta 保留原值
- **FR-010**: 系统 MUST 限制 HTTP 并发数 ≤ 5（asyncio.Semaphore），含正常搜索路径和回灌脚本路径
- **FR-011**: 系统 MUST 在每次 meta 解析后输出结构化日志，含 url / duration_ms / status / cache_hit / source_tag
- **FR-012**: 系统 MUST 在 pytest 中可注入假 HTTP client（fixture 或 dependency injection），便于不联网的单元测试
- **FR-013**: 系统 MUST 在 `sources` 表新增 `source_time_method` 列（字符串枚举），写入时记录该条 source_time 是从哪种途径解析的；枚举值：`url_path / meta_og / meta_article_published / meta_publishdate / meta_pubdate / meta_itemprop_date / citation / snippet / null`
- **FR-014**: 回灌脚本 MUST 只重跑 `source_time_method IN ('citation', 'snippet', NULL)` 的行；已经标为 `url_path` 或 `meta_*` 的不重跑（避免对已核验数据反复 HTTP）

### Key Entities

- **MetaTimeResult（解析结果）**：url（输入）、published_at（datetime? UTC）、status（enum: matched / timeout / http_error / no_meta / error）、source_tag（命中的标签名，如 `og:published_time`）、duration_ms（int）、cache_hit（bool）
- **Source（既有表，新增字段）**：`source_time_method` (varchar(40), nullable) —— 记录 source_time 取值途径，可观测 + 回灌可重入

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 对一组 20 条真实「URL 无日期 + 有 og:published_time」样本，meta 解析成功率 ≥ 85%（人工抽查与原网页 meta 内容对比）
- **SC-002**: 单次 meta 解析 P95 ≤ 3 秒（含 HTTP GET + 正则匹配）；P99 ≤ 6 秒（含超时触发）；缓存命中 ≤ 100ms
- **SC-003**: 引入 meta 解析后，单次搜索的整体延迟 P95 增加 ≤ 5 秒（最多 5 个 meta 请求并发 × 1 秒平均）
- **SC-004**: 一次性回灌脚本跑完后，对 DB 里 232 条候选源人工抽样 10 条，准确率 ≥ 95%（误差 ≤ 1 天）
- **SC-005**: 假阳性率 = 0%（FR-006 时间合理性约束保证）—— 通过 pytest 覆盖未来时间 / 远古时间用例验证
- **SC-006**: 缓存命中率上线 1 周后 ≥ 40%（同一热门 URL 被多次搜索）

## Assumptions

- 主流目标网站（smzdm / 知乎专栏 / 大部分 CMS 类网站）的 og:published_time / article:published_time meta 标签在 SSR HTML 里已就绪，httpx 一次 GET 即可拿到
- 当前后端环境（venv）已装 httpx（spec-006 引入），无需新依赖
- spec-002 的 URL 路径日期匹配规则仍生效，本 spec 仅作为「URL 无日期」时的兜底
- Redis 容器 + cache 模块 spec-006 已落地，本 spec 直接复用 namespace 模式
- 反爬墙 / 登录墙 / 严格 Referer 检查的网站会被自动归入 `http_error` / `no_meta` 降级 —— 这是可接受的损失（少量信源仍依赖 spec-002 原 fallback）
- 一次性回灌脚本运行时机：本 spec 上线后立即跑一次；之后理论上不需要再跑（新搜的数据走新路径自动准）
