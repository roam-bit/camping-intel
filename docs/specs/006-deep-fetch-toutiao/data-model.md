# Phase 1 Data Model: 深抓相关实体

**Date**: 2026-05-20

本文件描述 spec-006 引入的实体（dataclass / Pydantic / DB column 三个层级），含字段、约束、生命周期。

---

## 实体 1：`TopicPagePost` —— 候选单帖（in-memory only）

**用途**：Playwright 抓到的单条帖子在内存中的表示，**不**持久化到 PostgreSQL。

| 字段 | 类型 | 必填 | 约束 / 说明 |
|---|---|---|---|
| `title` | `str` | ✅ | 单帖标题；空字符串视为缺失 → 不入候选集 |
| `text_excerpt` | `str` | ✅ | 正文前 500 字（截断）；空字符串不入候选集 |
| `published_at` | `datetime \| None` | ❌ | 解析失败为 None，不阻止入候选 |
| `permalink_url` | `str` | ✅ | 单帖固定 URL；必须是 http(s) 协议、绝对路径；否则不入候选 |

**生命周期**：
- 由 `PostFetcher.fetch(url)` 返回 `list[TopicPagePost]`
- 由 `RelevanceScorer.pick_top(posts, keyword)` 消费
- 命中后字段被 ① 直接序列化进 Redis 缓存 ② 透传给 service 调用方
- **不**进 PostgreSQL

**实现层**：`backend/app/services/fetchers/base.py` 用 `dataclass` 定义。

---

## 实体 2：`DeepFetchResult` —— 深抓结果（in-memory + Redis）

**用途**：单次深抓的完整产出，跨服务层 / router 层 / 缓存层共享。

| 字段 | 类型 | 必填 | 约束 / 说明 |
|---|---|---|---|
| `source_url` | `str` | ✅ | 输入的原话题页 URL |
| `keyword` | `str` | ✅ | 输入的搜索关键词（归一化后） |
| `matched_post` | `TopicPagePost \| None` | ❌ | 命中时填，未命中为 None |
| `top_score` | `float` | ✅ | 0.0-1.0；未命中为 0.0 |
| `match_status` | `Enum` | ✅ | `matched / no_match / timeout / error` 之一 |
| `duration_ms` | `int` | ✅ | 端到端耗时（含 Playwright + LLM） |
| `posts_extracted` | `int` | ✅ | 渲染出的候选单帖总数 |
| `fallback_mode` | `Enum` | ✅ | `none / keyword_only` —— 标识是否走了 LLM 失败兜底 |
| `cache_hit` | `bool` | ✅ | 默认 False；缓存命中路径返回时 True |

**状态机**：
```text
[start] ─► render_page ─► extract_posts ─► score_relevance ─► [done]
              │                  │                  │
              └─► timeout        └─► no_posts      └─► top_score<threshold
                  match_status=  match_status=     match_status=
                  timeout        no_match          no_match
                  ▲
                  └─── any exception → match_status=error
```

**生命周期**：
- service 层组装 → router 层消费 → 同步写入 Redis（TTL 24h）
- 完整 JSON 结构同步用于结构化日志输出（FR-008）

**实现层**：`backend/app/services/deep_fetch_service.py` 用 `pydantic.BaseModel`（便于 Redis JSON 序列化）。

---

## 实体 3：`Place`（既有表）—— 增量字段

**Table**: `places`（既有，由 `backend/app/models/place.py` 定义）

| 字段（新增） | 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `topic_url_original` | `TEXT` | ❌ | `NULL` | 仅当深抓命中（match_status=matched）时填；存原话题页 URL，方便后续溯源 / debug |

**Migration**：`alembic/versions/006_add_topic_url_original.py`
- `ADD COLUMN topic_url_original TEXT NULL`
- 不需要回填历史数据（POC 阶段话题页已被 `is_topic_aggregator_url` 拦在外面，places 表里不应该有"假话题页"残留；如果有，等本期上线后人工清理）
- 回滚：`DROP COLUMN`

**既有字段引用**（无变动，仅说明协作关系）：
- `source_url` —— 命中时**被替换**为单帖 permalink；未命中时**整体剔除**（不再保留话题页 URL）
- `location_confidence` —— 深抓失败（含 timeout/error/low score）时强制设为 `low`；让 spec-004 过滤层把它挡在 marker 之外

---

## 实体 4：缓存条目（Redis）

**Key 格式**：`deep_fetch:v1:{md5_hex(topic_url + "|" + keyword_normalized)}`

**Value**：`DeepFetchResult` 的 JSON 序列化（含所有字段）

**TTL**：86400 秒（24h）

**Namespace 隔离**：所有本 spec 缓存统一前缀 `deep_fetch:v1:`，方便 ops 整体 invalidate（`SCAN MATCH deep_fetch:v1:* | DEL`）

**Eviction 策略**：依赖 Redis 默认 `maxmemory-policy`（生产配 `allkeys-lru`），TTL 优先于 LRU

---

## 关系图（简版）

```text
search request (router)
  │
  ▼
ai_service.public_fact_source_dict() ─► 命中 is_topic_aggregator_url=True
  │
  ▼
deep_fetch_service.fetch_and_match(url, keyword)
  ├── Redis GET cache_key → 命中返回 DeepFetchResult
  └── 未命中：
        ├── (Semaphore: process ≤ 3, request ≤ 2)
        ├── PostFetcher.fetch(url) → list[TopicPagePost]
        ├── RelevanceScorer.pick_top(posts, keyword) → (TopicPagePost?, score)
        ├── 组装 DeepFetchResult
        └── Redis SETEX (TTL 24h)
  │
  ▼
router 组装响应
  ├── matched：源 URL 替换为 matched_post.permalink_url，places.topic_url_original = 原 url
  └── not matched：从信源 chip 列表整体剔除该 URL；places.location_confidence='low'
```
