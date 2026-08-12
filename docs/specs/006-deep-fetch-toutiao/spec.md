# Feature Specification: 微头条话题页单帖深度抓取（Phase 1）

**Feature Branch**: `006-deep-fetch-toutiao`

**Created**: 2026-05-20

**Status**: Draft

**Input**: User description: "微头条话题页单帖深度抓取（spec-006，Phase 1）—— AI 信源若是 weitoutiao.zjurl.cn 的话题汇总页，后端渲染抓页内帖，按搜索关键词筛出 1 条最相关单帖，替换信源 URL；失败时降级。"

## Clarifications

### Session 2026-05-20

- Q: 同一个话题页+关键词组合的深抓结果，要不要缓存？ → A: Redis 缓存 24 小时（key = url+keyword 哈希，跨进程共享，复用现有 Redis 容器）
- Q: 多用户同时搜索时 Playwright 全局并发要不要限？ → A: 进程级全局 semaphore ≤ 3 + per-request ≤ 2（两层防护，单实例足够）
- Q: 抓到的单帖元数据要不要持久化到 places 表？ → A: 只存 Redis 24h（跟 Q1 缓存一致），places 表只落 source_url + topic_url_original 两个指针；详情抽屉展示摘要走 Phase 3 OSS 预存独立立项
- Q: 深抓失败（no_match/timeout/error）时，原话题页要不要还显示在用户可见的信源 chip 列表里？ → A: 整体剔除 —— 信源宁少不滥，前后一致；与 location_confidence=low 过滤 marker 的逻辑对齐

## User Scenarios & Testing *(mandatory)*

### User Story 1 - 话题页信源自动落到具体单帖（Priority: P1）

用户搜索一个露营点（如「莫干山」），AI 返回的信源列表里有一条来自微头条的话题汇总页（如 `#免费露营地#` 话题页）。**用户希望点开看到的是「网友实际在莫干山露营的具体单帖」，而不是一个聚合了几十个无关地点的话题页**。

**Why this priority**：这是 P1，因为话题页混入信源直接破坏产品「信源求证」的核心承诺——用户点进去看到的内容和搜索词无关，会立刻丧失对 AI 信源质量的信任。POC 阶段的过滤只能丢弃话题页，丢失了里面真正高质量的 UGC；本故事是「保留富矿、过滤噪音」的关键。

**Independent Test**：给定一个真实的微头条话题页 URL + 关键词「莫干山」，调用后端深抓接口，能返回 1 条该话题页内的具体单帖 permalink，且单帖正文/标题包含「莫干山」。无需前端改动即可在 API 层验证。

**Acceptance Scenarios**:

1. **Given** 一条信源 URL 被识别为微头条话题页，**When** 后端对该 URL 启动深抓 + 关键词「莫干山」，**Then** 30 秒内返回 1 条该话题页内的具体单帖 permalink，且该帖标题或正文包含「莫干山」或近义地名
2. **Given** 用户搜索「莫干山露营」**When** 完整搜索 pipeline 跑完，**Then** 落到 places 表的点位 source_url 字段是单帖 permalink，topic_url_original 字段保留原话题页 URL
3. **Given** 一条非话题页的普通信源 URL，**When** 后端处理该信源，**Then** 不触发深抓逻辑（直接走原有流程，避免误抓）

---

### User Story 2 - 抓不到相关单帖时安全降级（Priority: P1）

如果话题页里**没有**任何一条单帖与搜索关键词相关（例如「莫干山」话题里只有西藏内容），系统**绝不能编造**或随便返回一个不相关单帖来糊弄用户；且失败的话题页 URL 应从前端可见的信源 chip 列表里**整体剔除**，避免用户点开看到的还是混乱话题页。

**Why this priority**：和 Story 1 同等关键。返回错的信源比返回话题页更糟糕——用户会误以为这是 AI 验证过的「点位证据」，实际是无关内容。这条是「宁可空、不可错」的安全护栏。

**Independent Test**：构造一个 mock 话题页（所有帖子都与「莫干山」无关），调用深抓接口，应返回 null + 原话题页 URL；且产生的 places 记录 location_confidence 降级为 `low`。

**Acceptance Scenarios**:

1. **Given** 话题页内无任何单帖匹配关键词，**When** 深抓完成筛选，**Then** 接口返回 `matched_post=null`，源 URL 保留为原话题页，且对应 places 记录 location_confidence=`low`（受 spec-004 过滤逻辑保护，不会出现在用户地图上）
2. **Given** Playwright 渲染该话题页超过 15 秒未完成，**When** 超时触发，**Then** 接口返回 `matched_post=null` + 原话题页 URL，且记录 fetch_status=`timeout`，不抛 500 错误污染上层 pipeline

---

### User Story 3 - 深抓延迟可观测（Priority: P2）

后端工程师/PM 希望能从日志/metrics 上看到「这次搜索里深抓花了多少秒、命中了几条、失败几条」，便于后续判断是否要扩展到知乎/小红书（Phase 2），或者是否要把 Playwright 抽成独立微服务。

**Why this priority**：可观测性是 P2 因为不直接影响用户体验，但缺了它，PM 无法判断这个能力的 ROI、也无法发现回归（例如某天微头条改版了导致深抓全 timeout）。

**Independent Test**：跑一次包含话题页的搜索，看后端 stdout 日志里有 `deep_fetch.duration_ms` / `deep_fetch.posts_extracted` / `deep_fetch.match_status` 三个字段。

**Acceptance Scenarios**:

1. **Given** 一次搜索触发了 N 次深抓，**When** 搜索完成，**Then** 后端日志可见 N 行结构化日志，每行至少含 `url, duration_ms, posts_extracted, match_status (matched/no_match/timeout/error)`

---

### Edge Cases

- 话题页 URL 实际重定向到登录页 / 反爬墙 / 404：归入 `error` 状态，降级为返回原 URL，不抛错。
- 单帖筛选时 LLM 调用失败：降级为「关键词字面匹配」选第一条命中的单帖，仍然返回结果；记录 `fallback=keyword_only`。
- 同一次搜索里出现 ≥3 条话题页信源：并发深抓但限流（最多并发 2 个 Playwright 实例），避免本地资源耗尽。
- 话题页内只有 1 条单帖：直接返回该单帖（无需 LLM 筛选），节省一次 LLM 调用。
- 单帖正文里没有显式关键词但有图片定位（如纬经度 EXIF）：本期不处理，归入 Phase 2 范围。

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: 系统 MUST 能识别一个信源 URL 是否属于「微头条话题页」类型（复用现有 `is_topic_aggregator_url` 判断，扩展该函数返回 `is_toutiao_topic=True`）
- **FR-002**: 系统 MUST 对识别为微头条话题页的 URL 自动触发深抓流程，无需用户/上游主动指定
- **FR-003**: 系统 MUST 用浏览器渲染引擎抓取页内每条帖子的：标题、正文前 500 字、发布时间、单帖 permalink URL（4 个字段缺一不可入候选集）
- **FR-004**: 系统 MUST 在候选集 ≥1 条时，按「搜索关键词与单帖（标题+正文）的相关性」排序，返回 Top 1
- **FR-005**: 系统 MUST 候选集中 Top 1 的相关性分数 ≥ 阈值（默认 0.6）才返回该单帖；低于阈值视为 no_match
- **FR-006**: 系统 MUST 在以下情况返回 `matched_post=null` 并保留原话题页 URL：(a) 渲染超时 ≥15s (b) 候选集为空 (c) Top 1 相关性 < 阈值 (d) LLM 调用失败且关键词字面也匹配不到
- **FR-007**: 系统 MUST 在写入 places 表时，把单帖 permalink 写入 `source_url`、原话题页 URL 写入新字段 `topic_url_original`（可空，仅命中时填充）
- **FR-008**: 系统 MUST 在每次深抓后输出结构化日志，含 `url, duration_ms, posts_extracted, match_status, top_score`
- **FR-009**: 系统 MUST 限制并发深抓资源：(a) 同一次搜索请求内并发深抓数 ≤ 2，(b) 整个后端进程级全局并发深抓数 ≤ 3（两层 semaphore 防护，避免多用户同时搜索时本地 Playwright 资源耗尽）
- **FR-010**: 系统 MUST 对深抓失败（任何原因）的话题页对应点位标记 `location_confidence=low`，让 spec-004 过滤层把它挡在用户地图之外
- **FR-011**: 系统 MUST 提供一个可在 pytest 中 mock Playwright 输出的接口边界（依赖注入或 protocol 抽象），便于 happy-path 和 timeout 两条 regression 测试
- **FR-012**: 系统 MUST 缓存每次深抓的最终结果（含命中/未命中状态），缓存 key 由「话题页 URL + 搜索关键词」组合哈希得出；缓存 TTL = 24 小时；缓存命中时跳过 Playwright + LLM，直接返回缓存值并在日志标注 `cache_hit=true`
- **FR-013**: 系统 MUST 在深抓失败（match_status ∈ {no_match, timeout, error}）时，**从最终返回给前端的信源列表里整体剔除该话题页 URL**（不只剔除地图 marker），保证信源 chip 与地图点位一致 —— 用户点信源 chip 看到的页面**永远**和搜索词相关

### Key Entities

- **TopicPagePost（候选单帖）**：title (str), text_excerpt (str, ≤500 字), published_at (datetime?), permalink_url (str)
- **DeepFetchResult（深抓结果）**：source_url (原话题页), matched_post (TopicPagePost?), top_score (float 0-1), match_status (enum: matched/no_match/timeout/error), duration_ms (int), fallback_mode (enum: none/keyword_only)
- **Place（既有表，新增字段）**：`topic_url_original` (text, nullable) —— 仅当深抓命中时填充；单帖标题/摘要/发布时间**不**进 places 表，只存 Redis 24h（合规零风险）

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 对一组 10 条真实「微头条话题页 + 搜索关键词」样本，≥ 7 条能返回与关键词强相关的具体单帖（人工判定）—— 即"信源替换成功率 ≥ 70%"
- **SC-002**: 单次深抓在 P95 下 ≤ 20 秒完成（含渲染 + 抽取 + LLM 筛选）；P99 ≤ 30 秒（含超时触发）
- **SC-003**: 当深抓应该 no_match 时，系统**永远不返回错误的单帖**（即「假阳性率 = 0%」）—— 通过 mock 测试 + 上线后人工抽查 20 条结果验证
- **SC-004**: 用户在搜索结果页点击信源 chip 后，看到的页面是「能直观判断与点位相关」的概率从基线 30%（POC 阶段含话题页时）提升到 ≥ 80%（命中后跳单帖）—— 通过演示场景人工评分
- **SC-005**: 引入深抓后，整次搜索的端到端延迟 P95 增加 ≤ 10 秒（即对用户体感影响可控）
- **SC-006**: 缓存命中场景下（重复搜索同一话题页+关键词），深抓阶段端到端延迟 ≤ 100ms（仅 Redis 一次往返）

## Assumptions

- 用户使用普通家用网络访问微头条话题页，不依赖代理/VPN（演示环境一致）
- 微头条 SPA 页面在公开访问时**不需要登录**就能看到帖子列表（截至 2026-05 实测仍然成立）
- 当前后端运行环境（本地 venv + 阿里云后续部署）可以安装并运行 Playwright + Chromium（约 300MB）
- 复用现有 Ark Seed 2.0 provider 做 LLM 相关性打分，单次调用约 1-3 秒，prompt 可控制在 200 token 内
- spec-004 的 location_confidence=low 过滤已上线，本 spec 直接复用该兜底层
- 本 spec 不引入新的外部服务（如独立爬虫微服务、OSS）—— 这些是 Phase 3 范围
- Playwright 抽象成一个 fetcher 接口，pytest 用 fake fetcher 注入即可，无需在 CI 真实跑浏览器
