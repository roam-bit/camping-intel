# Phase 1 Data Model: meta_time 服务

**Date**: 2026-05-20

---

## 实体 1：`MetaTimeResult` —— 解析结果（in-memory + Redis）

| 字段 | 类型 | 必填 | 约束 / 说明 |
|---|---|---|---|
| `url` | `str` | ✅ | 输入的信源 URL |
| `published_at` | `datetime \| None` | ❌ | UTC；matched 时填值，其它状态为 None |
| `status` | `Enum` | ✅ | `matched / timeout / http_error / no_meta / error` |
| `source_tag` | `str \| None` | ❌ | 命中的标签名（`og:published_time` / `article:published_time` / ...）；非 matched 为 None |
| `duration_ms` | `int` | ✅ | 端到端耗时（含 HTTP + 解析） |
| `cache_hit` | `bool` | ✅ | 默认 False；缓存命中路径返回 True |

**状态机**：

```text
[start] ─► HTTP GET (timeout 5s) ─► parse <head> meta ─► validate range ─► [done]
            │                          │                    │
            └─► timeout                └─► no meta tag       └─► out of [2010, now+1d]
                status=timeout         status=no_meta         status=no_meta
            └─► 4xx/5xx
                status=http_error
            └─► any other exception
                status=error
```

**实现层**：`backend/app/services/meta_time_service.py` 用 `pydantic.BaseModel`。

---

## 实体 2：`Source`（既有表）—— 增量字段

**Table**: `sources`（既有，由 `backend/app/models/source.py` 定义）

| 字段（新增）| 类型 | 必填 | 默认 | 说明 |
|---|---|---|---|---|
| `source_time_method` | `VARCHAR(40)` | ❌ | `NULL` | 记录 source_time 取值途径，枚举值见下 |

**枚举值**：`url_path / meta_og / meta_article_published / meta_publishdate / meta_pubdate / meta_itemprop_date / citation / snippet`（NULL = 未尝试 / 未知）

**Migration**：`alembic/versions/0004_add_source_time_method.py`
- `ALTER TABLE sources ADD COLUMN source_time_method VARCHAR(40) NULL`
- 不回填历史值 —— 历史数据 method 为 NULL，回灌脚本据此识别要重跑
- 回滚：`DROP COLUMN`

**既有字段引用**（无变动）：
- `source_time` —— 取值来源逻辑变更：spec-007 上线后优先来自 meta；标 method 字段同步写

---

## 实体 3：Redis 缓存条目

**Key 格式**：`meta_time:v1:{md5_hex(url)}`

**Value**：`MetaTimeResult` 的 JSON 序列化（不含 cache_hit 字段，命中时由 service 层补 True）

**TTL**：86400 秒（24h）

**Namespace 隔离**：所有本 spec 缓存统一前缀 `meta_time:v1:`，方便 ops 整体 invalidate

---

## 关系图

```text
sources_from_citations(citations) ─► resolve_published_at(url, citation, snippet)
                                          │
                                          ├── extract_date_from_url(url) ── 命中 → method=url_path
                                          │
                                          ├── (新增) resolve_meta_published_at(url)
                                          │       │
                                          │       ├── Redis GET → 命中返回 MetaTimeResult
                                          │       └── 未命中：
                                          │             ├── (Semaphore: process ≤ 5)
                                          │             ├── httpx.AsyncClient.get(timeout=5s)
                                          │             ├── 截取前 256KB → re 匹配 5 个 meta tag
                                          │             ├── 时间合理性校验 [2010, now+1d]
                                          │             ├── 组装 MetaTimeResult
                                          │             └── Redis SETEX 24h
                                          │
                                          ├── parse_source_date(citation_published_at) ── 命中 → method=citation
                                          │
                                          └── parse_source_date(snippet) ── 命中 → method=snippet
```

---

## 回灌脚本数据流

```text
backfill_meta_time.py
  ├── SELECT * FROM sources WHERE source_time IS NOT NULL
  │     AND source_time_method IN ('citation', 'snippet') OR source_time_method IS NULL
  │     AND source_url !~ 'YYYY/MM/DD pattern'   # 双重保险
  │
  ├── 按 URL 去重（同 URL 多 sources 行只抓 1 次）
  │
  ├── 并发 asyncio.gather(Semaphore 5) → resolve_meta_published_at(url)
  │
  ├── 对每条解析结果：
  │     - matched: UPDATE source_time + source_time_method = meta_*
  │     - 其它状态: 仅 UPDATE source_time_method = 当前值（保留 source_time 不变）
  │
  └── 输出统计:
        - 扫描 N 条
        - 成功更新 X 条
        - 域名级成功率（top 10）
        - 失败原因分布
```
