# Phase 0 Research: 信源时间 HTML meta fallback

**Date**: 2026-05-20

---

## D1：HTML 解析策略 —— 正则 vs BeautifulSoup vs lxml

**Decision**：纯 stdlib `re`（编译好的正则常量）

**Rationale**:
- meta 标签结构高度规范（`<meta property="X" content="Y">`），正则足够；不需要完整 DOM 树
- 不引入新依赖（BeautifulSoup 装 ~600KB；lxml 装 ~2MB + C 编译）
- 性能：re 匹配 ~1ms，DOM 解析 ~10-50ms（10x+ 慢）
- 局限：HTML 不闭合标签 / 复杂引号嵌套 → 接受这些极端情况返回 None（降级到原 fallback 链）

**Alternatives considered**:
- BeautifulSoup → 强大但 overkill，meta 抽取用不上 DOM 树遍历
- lxml → 性能最好但部署增加 C 编译依赖（阿里云 musl libc 时有坑）
- pyquery / selectolax → 同等复杂度，无明显优势

**Implementation note**：用 `re.IGNORECASE | re.DOTALL` 标志，覆盖 `<meta Property="OG:..."` 大小写变体。

---

## D2：HTTP 抓取策略 —— UA / Referer / 限流

**Decision**：默认 httpx UA（不模拟浏览器）+ 进程级 `asyncio.Semaphore(5)` + 5s timeout + 256KB 体积上限

**Rationale**:
- 主流目标网站（smzdm / 知乎 / 多数 CMS）对 meta 标签不做反爬，默认 UA 够用
- 反爬严格的站（特定头部 / 登录墙）天然归入 `http_error` / `no_meta` 降级 —— **可接受的损失**（这部分占少数）
- Semaphore(5) 全局复用（含搜索路径 + 回灌脚本），跟 spec-006 的限流策略对齐
- 5s timeout 严卡 —— 慢站不让它拖死整次搜索
- 256KB 体积：meta 标签都在 `<head>`，绝大多数网页 head < 50KB；256KB 已是 5x 余量

**Alternatives considered**:
- 模拟浏览器 UA（Mozilla/Chrome）→ 命中率可能略升但触发更严格反爬的风险也升，且**不可观测**（看不到目标站对哪种 UA 限流）
- 加 Referer → 单站策略不同，无统一规则；省略
- 不限流 → 多用户并发时把目标站 DDoS，被封域名风险高
- 用 head request 只取头部 → meta 标签必须 GET 才能拿到内容，head 不行

---

## D3：缓存策略

**Decision**：`meta_time:v1:{md5(url)}`，TTL = 24h，value = JSON `{published_at: iso|null, source_tag: str|null, status: enum}`

**Rationale**:
- 跟 spec-006 缓存模式对齐（同 namespace 前缀 + v1 + md5 + 24h）
- **失败也缓存**：避免对一直失败的站点反复抓（如 404 / 反爬），24h 后才再试一次
- md5(url) 是 URL 唯一性的稳定 key；不归一化（URL 本身已经是规范化的，没有 keyword 这种用户输入维度需要 NFKC）
- Value 存完整 status + source_tag → 缓存命中也能输出完整日志，可观测性不打折扣

**Alternatives considered**:
- 永久缓存 → 网站文章 republish 时拿到旧时间；24h 是新鲜度兜底
- 只缓存成功结果 → 失败的同 URL 反复抓
- 缓存到 PostgreSQL → 加表 + 多一次查；Redis 更轻

---

## D4：fallback 链插入位置

**Decision**：`URL → meta → citation → snippet`（meta 放第 2 位，citation 之前）

**Rationale**:
- meta 是自动化元数据（CMS 自动写入），比 citation（Ark LLM 抽出来的字段）可信
- meta 是真实页面源，citation 是 Ark 中介层，meta 离真相更近
- 与 clarify Q2 用户决议一致（meta 优先）

**Alternatives considered**:
- 放第 1 位（URL 之前）→ 会对所有 URL 都发 HTTP 请求，浪费带宽（人民网这种 URL 含日期的根本不需要 meta）
- 放第 3 位（citation 之后）→ 如果 citation 错就被 citation 拦截，meta 永远不调用 —— 完全失去意义

**实施约束**：URL 路径解析 (`extract_date_from_url`) 命中时**短路**返回，不调 meta；只有 URL 解析 = None 才进入 meta 阶段。

---

## D5：source_time_method 字段设计

**Decision**：新增 `source_time_method VARCHAR(40) NULL`，枚举值：

| 值 | 含义 |
|---|---|
| `url_path` | spec-002 URL 路径含日期解析 |
| `meta_og` | og:published_time 命中 |
| `meta_article_published` | article:published_time 命中 |
| `meta_publishdate` | publishdate 命中（中文站）|
| `meta_pubdate` | pubdate 命中 |
| `meta_itemprop_date` | itemprop=datePublished 命中 |
| `citation` | Ark citation.published_at（不可信）|
| `snippet` | 文本启发式抽取（最不可信）|
| `NULL` | 未尝试 / 无来源 |

**Rationale**:
- 字符串枚举比 int enum 直观（DB CLI 查得清楚）
- 40 字符够长，未来加新 method 不需要 migration
- NULL 保留：历史数据（spec-007 之前）一律为 NULL，回灌脚本据此识别"需要重跑"
- 回灌脚本只重跑 `IN ('citation', 'snippet', NULL)` 的行（FR-014）

**Alternatives considered**:
- enum 类型（PG ENUM）→ 加新值要 ALTER TYPE，DBA 操作；varchar 更灵活
- bool `time_verified` → 信息量太少，看不出 method
- 拆成多列（method + extracted_meta_tag）→ 冗余

---

## D6：回灌脚本运行模式

**Decision**：standalone Python 脚本 `scripts/backfill_meta_time.py`，独立连 DB 直接 SQL，跟 FastAPI app 解耦

**Rationale**:
- 一次性脚本，不需要 HTTP API 入口
- 独立连 DB（用 SQLAlchemy session）便于运维直接 `python scripts/backfill_meta_time.py` 跑
- 共用 `meta_time_service.resolve_meta_published_at`（同一逻辑，避免双份）
- 跑完输出结构化报告：扫描 N 条 / 成功 X 条 / 跳过 Y 条 / 失败 Z 条 + 域名级统计

**Alternatives considered**:
- alembic data migration → migration 跑外网 HTTP 是反模式，且无法重跑
- FastAPI admin endpoint → 需要鉴权 + 调用方便管控，但单次维护任务不值得
- celery 异步任务 → 引入新基础设施

---

## 综合结论

所有技术决策已确定，可进入 Phase 1。后续 Phase 2/3 关注点（本期不做）：
- 多语言 meta 标签兼容（俄文/日文 published_time 变体）
- 站点级 fallback 规则（特定站使用 sitemap.xml 而非 meta）
- 时间格式宽松解析的更复杂场景（"两周前" 这种相对时间）
