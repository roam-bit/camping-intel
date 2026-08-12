# Feature Specification: 信源发布时间显示准确性修复

**Feature Branch**: `002-fix-source-date`

**Created**: 2026-05-18

**Status**: Clarified（3 个澄清问题已答，可进 plan）

## Clarifications

### 2026-05-18 Round 1

- **Q1：URL 不含日期 + citation 也无 published_at 时，加 HTML meta 抓取吗？** → **不加**，保持最小改动。HTML meta 抓取引入额外 HTTP 调用 + 不稳定性，本次不在范围；仍 fallback 到 snippet 抽日期。
- **Q2：URL 抽日期 vs citation.published_at 冲突信谁？** → **信 URL**，无条件。URL 路径里的日期是网站发布时写死的，不会改；citation 是 Ark 给的可能含索引时间。
- **Q3：要不要回填旧数据？** → **不动旧数据**。只修生成逻辑（parse_source_date + 调用方），下次 AI 重抽自然刷新。

**Input**: 用户对比截图发现：产品里「柚子营地」详情页底部信源卡片显示「sh.people.com.cn · 2026-04-22」，但原文人民网页面（同一篇文章）实际发布时间是「2024-11-08 19:18」。AI 提炼板块的"信息日期"对（2024-11-08），但卡片底部展示错（2026-04-22）。

## User Scenarios & Testing *(mandatory)*

### User Story 1 - 信源日期与原文真实发布时间一致（Priority: P1）

用户在产品里看到某条信源（比如人民网"上海发布帐篷露营地白名单"），底部展示的发布日期必须**等于该网页实际的发布时间**，不能是爬虫的"索引时间"或其他无关日期。

**Why this priority**: 这是信息可信度的**核心契约**。用户基于"信源日期"判断信息新旧（演示时也是）。一旦发现"原文 2024，产品显示 2026"，用户会**整体怀疑数据真实性**。

**Independent Test**: 在浏览器搜「上海露营地」，点开任一来自人民网的信源卡片（域名 `*.people.com.cn`），断言底部日期 = 原文 HTML `<meta>` 或 URL 路径里的真实发布日期，**误差为 0**。

**Acceptance Scenarios**:

1. **Given** 信源 URL 是 `sh.people.com.cn/n/2024/1108/c134768-...`（URL 含日期路径）, **When** AI 抽取并展示该信源, **Then** 卡片底部日期 = **2024-11-08**（而不是爬取时间）
2. **Given** 信源 snippet 包含 "2026-04-22 更新" 和原文真实发布日期 "2024-11-08", **When** AI 解析日期, **Then** 优先取 URL 里的 2024-11-08，**不取** snippet 里的爬取时间
3. **Given** AI 提炼板块文字写「信息日期 2024-11-08」, **When** 用户看同一条信源的卡片底部, **Then** 显示一致的 **2024-11-08**

---

### User Story 2 - URL 不含日期时优先用 HTML meta（Priority: P2）

并非所有信源 URL 都含日期路径（比如知乎/小红书/搜狐 mobile）。这种情况下应该**优先用 HTML `<meta>` 里的 published_time**，而不是 snippet 文本里的第一个 20YY-MM-DD（可能是错的）。

**Why this priority**: 覆盖 URL 抽不到日期的场景。优先级 P2 是因为 P1（URL 抽日期）已经能解决主流新闻站（人民网、新华网、地方党报、sohu 资讯频道等格式规范的），P2 是补充。

**Independent Test**: mock 一个无日期 URL（如 `news.qq.com/rain/a/xxx`）+ snippet 含多个日期，断言系统取的是 HTML meta 而非 snippet 头部的日期。

**Acceptance Scenarios**:

1. **Given** URL 是 `news.qq.com/rain/a/20260512A04QJ500`（含日期 20260512）, **When** 解析, **Then** 用 URL 里的 2026-05-12 而不是 snippet
2. **Given** URL 完全无日期（如 `mp.weixin.qq.com/s/xxx`）, **When** 解析, **Then** fallback 到原网页 HTML meta（如果可抓）或 AI 模型自己 parse 的 published_at

---

### User Story 3 - snippet 抽日期作为最后 fallback（Priority: P3）

当 URL 和 HTML meta 都拿不到时，**才**走 snippet 文本抽日期。这是现状逻辑，作为兜底**保留**（避免 0 信息状态）。

**Why this priority**: 现状逻辑保留是回归防护，**不要**因为修 P1/P2 把这条 fallback 链断掉。

**Independent Test**: mock URL 和 HTML meta 都没日期 + snippet 含"发布于 2025-03-10"，断言取到 2025-03-10。

**Acceptance Scenarios**:

1. **Given** URL/HTML 都拿不到日期, snippet 写「发布于 2025-03-10」, **When** 解析, **Then** 取 2025-03-10
2. **Given** snippet 同时含"2026-04-22 爬取" 和"发布于 2024-11-08", **When** 解析, **Then** 由于 P1/P2 都失败才走 P3，**承认歧义**，可以选第一个 20YY；如果**有 P1/P2 数据**就不该走到 P3

---

### Edge Cases

- **URL 含错误年份**（人为构造或 cms 路径与真实发布时间不一致）：本次相信 URL（最稳的近似真理）；以后用户报错再改
- **HTML meta 抓不到**（动态渲染 SPA）：不在本次范围，保持现状
- **snippet 里"2026-04-22"是真实更新时间**（不是爬取时间，是网站自己显示的）：本次仍按 URL 优先（错率 < snippet）
- **日期格式怪异**：如 `2024年11月8日`、`Nov 8, 2024` —— 当前 `parse_source_date` 正则只认 `20YY[-/.年]M[-/.月]D`，本次**不扩展**（保持现状）
- **同一 source 多次 AI extract，重复 parse 日期**：cache 已有，不重复（不在本 spec 范围）

---

## Requirements *(mandatory)*

### Functional Requirements

#### 后端解析逻辑

- **FR-001**: 后端 `parse_source_date(value)` 函数 **MUST** 接受 URL 字符串并能从中识别 `/20YY/MM/DD/`、`/20YY/MMDD/`、`/n/20YY/MMDD/...` 等常见路径模式
- **FR-002**: 后端 source 构造时 **MUST** 按以下**优先级**确定 `published_at`：
  1. 从 `source.url` 抽日期（用 FR-001 增强后的 parse）
  2. citation 字典自带的 `published_at` / `updated_at` 字段（Ark 等 search provider 返回的）
  3. **不再** 直接 parse `snippet`（这是当前 bug 源）—— snippet 只在前两者都失败时作为最后 fallback
- **FR-003**: 当 `source.source_time`（数据库已存）跟 `source.url` 抽出的日期**不一致**（差 > 30 天）时，**MUST** 信任 URL 抽的，**覆盖** source.source_time
- **FR-004**: `public_source_from_model` 和 `public_source` 函数 **MUST** 输出 `source_time` 字段（不只是 `published_at`），让前端 `sourceDate()` 优先级一致

#### 前端展示

- **FR-005**: 前端 `sourceDate(source)` 行为不变（优先级：source_time > updated_at > published_at），但**前提是后端配合输出 source_time**（见 FR-004）
- **FR-006**: 若同一 Place 的「AI 提炼信息日期」与「信源卡片日期」不一致，**MUST** 显示前者（AI 文本抽的更准）—— 实际上修了 FR-002 之后这两者应该自动一致

### Key Entities

- **Source**: 信源（数据库表），核心时间字段 `source_time`（应该 = 网页真实发布时间）
- **Citation**: AI（Ark）联网搜索返回的 dict，含 `url / title / snippet / published_at / updated_at`
- **PublishedAt**: 信源的"原文发布时间"，是真理基准（区别于"爬取时间"和"索引时间"）

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 搜「上海露营地」后，所有 `*.people.com.cn` 域名的信源卡片**日期** = URL 路径中的日期（**100% 准**）
- **SC-002**: 同一 Place 的「AI 提炼信息日期」与「信源卡片日期」一致率 **100%**（之前是 0%）
- **SC-003**: 5 条 regression test 覆盖：
  1. `parse_source_date(url)` 能从 `/n/2024/1108/...` 抽出 2024-11-08
  2. `parse_source_date(url)` 能从 `/rain/a/20260512Axxx` 抽出 2026-05-12
  3. snippet 含 "2026-04-22"+ URL 含 2024-11-08 → 取 URL（2024-11-08）
  4. URL 无日期 + citation.published_at = "2024-11-08" → 取 citation
  5. URL 和 citation 都无 + snippet 含日期 → 取 snippet（fallback 不退步）
- **SC-004**: 重新跑现有 21 个非 spec-001 + 9 个 spec-001 测试 → **0 个回归**
- **SC-005**: 浏览器实测点开"柚子营地"信源卡片，底部日期 = **2024-11-08**

---

## Assumptions

- `parse_source_date` 函数当前实现是正则扫文本，**不识别 URL 路径模式** —— 本次扩展它
- citation 字典的 `published_at` 字段（Ark 返回的）**质量参差** —— 不是 100% 可信，所以让 URL 抽优先
- 当前数据库里 `source.source_time` 字段可能存了错日期（爬虫历史 bug）—— 本次**不批量回填修旧数据**，只修生成逻辑；旧数据自然刷新（下次 AI 重抽）
- HTML meta 抓取**不在本次范围**（FR-002 第 3 步的 fallback 仍是 snippet，FR-002 只重新排序优先级）
- AI 提炼文本里的"信息日期"已经准（用户截图证实），本次不动 AI prompt
