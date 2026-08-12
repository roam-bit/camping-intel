# Phase 0 Research: 微头条话题页深抓

**Date**: 2026-05-20

调研目标：消解 plan.md Technical Context 中的所有 NEEDS CLARIFICATION，并为 Phase 1 设计提供「为什么这么选」的依据。

---

## D1：渲染引擎选型

**Decision**：Playwright (Python async) + Chromium headless

**Rationale**:
- 微头条话题页是 SPA（首屏空 HTML + JS 渲染列表），必须用真浏览器；纯 `httpx` + 解析 HTML 拿不到帖子列表
- 后端是 Python，Playwright 有官方 async API，跟现有 `async def` 服务层无缝
- Playwright 比 Selenium 启动快（约 1-2s vs 5s+），跟 SC-002 P95 20s 目标契合
- Chromium 镜像约 150MB，本地装一次；阿里云部署期再装一次成本可控

**Alternatives considered**:
- Puppeteer (Node) + Node 微服务 → 引入跨语言部署，单体后端复杂度暴涨，不值得
- Selenium → 启动慢、维护差，劣于 Playwright
- `requests-html` / `pyppeteer` → 维护停滞，2024+ 不推荐
- 直接调用今日头条移动端 API → 反爬 / 协议不公开 / 合规风险

---

## D2：相关性筛选策略

**Decision**：两层组合 —— L1 关键词字面匹配（必过）+ L2 LLM 评分（决出 Top 1，阈值 ≥ 0.6）

**Rationale**:
- L1 字面匹配：先把候选集从「页内全部帖子」缩到「标题或正文含关键词」的子集，确保 SC-003 假阳性率 = 0%（LLM 出错也不会返回完全不相关的）
- L2 LLM 评分：候选集 ≥ 2 时用 Ark 评估「关键词与单帖的语义相关性 0-1」，取 Top 1；候选集 = 1 时跳过 LLM 直接返回（节省调用）
- 阈值 0.6 来自直觉初始值——「莫干山」搜「莫干山免费露营点」打 0.8+ 容易；打到 0.5 通常意味着只是同省、不在点上。上线后据 SC-003 抽查回调

**Alternatives considered**:
- 纯 LLM 评分（无 L1 过滤）→ 万一 LLM 幻觉返回不在候选集里的 ID，灾难
- 纯关键词 + 阈值（无 LLM）→ 召回率高、精度差，「莫干山」会命中「莫干山下蹲了一只猫」
- BM25 / TF-IDF 排序 → 中文分词依赖额外组件（jieba 等），过度工程
- 向量相似度（embedding）→ 单次调用更慢，本期不必要

**Implementation note**：LLM prompt 严格限制返回 JSON `{post_id: <候选集内 ID>, score: <0-1>}`，并校验返回 ID 必须在候选集里——多一道护栏防幻觉。

---

## D3：缓存 key 设计

**Decision**：`deep_fetch:v1:{md5(topic_url|keyword_normalized)}`，TTL = 24h，value = JSON（含 match_status / matched_post 完整快照）

**Rationale**:
- 加 `v1:` 版本前缀 → 未来字段变了能整体 invalidate，不需要清整个 Redis
- `keyword_normalized` = 关键词 lower + 去空格 + NFKC 归一化 → 「莫干山 」「莫干山」命中同一缓存
- md5 后才 32 字节，比原始 URL 短、定长，Redis key 友好
- value 存完整快照（含 fallback_mode、posts_extracted 等日志字段）→ 缓存命中也能输出完整结构化日志，可观测性不打折扣
- 缓存命中和未命中走完全相同的路径，仅多一个 `cache_hit=true` 字段——避免分支爆炸

**Alternatives considered**:
- 永久缓存 → 话题页内容会变（新帖刷出来），永久缓存会让用户错过新内容
- 只缓存命中结果，no_match 不缓存 → 反而让"没用的话题页"被反复抓，浪费更多资源
- 缓存到 PostgreSQL → 加表 + alembic + 查询慢，比 Redis 劣

---

## D4：失败信源剔除的实现层级

**Decision**：在 `/api/v1/search` 响应组装的最后一步（router 层）做剔除，不在 ai_service 内层做

**Rationale**:
- ai_service 层的职责是「拿到结构化信源 + 抽点位」——它应该如实返回深抓结果，包括 `match_status`
- router 层是唯一知道「最终要返回给前端什么」的地方——在这层做剔除职责清晰
- 测试更易写：可以在 service 层验证 `match_status=no_match` 逻辑，在 router 层验证「失败信源不出现在响应」

**Alternatives considered**:
- ai_service 内直接 mutate 信源列表 → 副作用，单元测试难
- 前端做剔除 → 前端要懂 `match_status` 含义，污染前端逻辑

---

## D5：相关性阈值是否可配置

**Decision**：阈值放 `app/config.py`，环境变量 `DEEP_FETCH_RELEVANCE_THRESHOLD`（默认 0.6），不动态可调

**Rationale**:
- 阈值是 ops/PM 调参，写死会让 SC-003 假阳性出现时无法快速止血
- 但本期不需要"每个用户/搜索"维度个性化，环境变量足够

---

## D6：Playwright 实例生命周期

**Decision**：每次深抓 new context（不复用浏览器）；进程退出时 cleanup

**Rationale**:
- 复用 browser 实例理论上更快（省 1-2s 启动），但要处理 cookie/state 串号 / context crash 等长尾问题
- Phase 1 重稳定性 > 重性能；P95 20s 留够预算
- 复用方案归入 Phase 2 优化（如果届时实测延迟成瓶颈）

**Alternatives considered**:
- 全进程单例 browser → 串号 / 内存泄漏风险，调试成本高
- 池化（playwright-pool 等库）→ 引入新依赖，过度工程

---

## D7：fixture 怎么构造

**Decision**：从一个真实微头条话题页人工保存 HTML/JSON 快照到 `backend/tests/fixtures/toutiao_topic_page.json`（含 5 条 mock 帖子，3 条与「莫干山」相关、2 条无关），由 FakeFetcher 直接返回

**Rationale**:
- happy-path 测试断言「最相关的 1 条被选中」
- timeout regression 测试用 FakeFetcher 抛 `asyncio.TimeoutError`，断言降级路径
- 不在 CI 跑真浏览器：CI 跑真 Chromium 慢、易 flake，且需要外网。本期 CI 只跑 FakeFetcher 单元测试，集成测试人工跑

---

## 综合结论

所有 NEEDS CLARIFICATION 已解决，可进入 Phase 1 设计。后续 Phase 2 关注点（已记录、本期不做）：
- 浏览器实例池化
- 相关性阈值动态调整
- CI 集成真 Playwright 测试
- 多平台 fetcher（知乎/小红书）的 protocol 适配验证
