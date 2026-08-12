# Implementation Plan: 信源发布时间 HTML meta fallback

**Branch**: `007-meta-time-fallback` | **Date**: 2026-05-20 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/007-meta-time-fallback/spec.md`

## Summary

在 `resolve_published_at` 的 3 段式 fallback 中插入新一层「HTML meta 解析」（顺序：URL 路径 → **meta（新）** → citation → snippet）。当 URL 路径不含日期时（spec-002 兜底失败），用 httpx 一次 GET 抓 HTML，正则提取 `og:published_time` / `article:published_time` / `publishdate` / `pubdate` / `datePublished` 5 个 meta 标签其一；命中即作为真实发布时间。解析结果缓存 Redis 24h，failure 也缓存。同时给 `sources` 表加 `source_time_method` 字符串枚举列以可观测 + 回灌可重入。配套一次性脚本 `scripts/backfill_meta_time.py` 修历史 232 条候选数据。

**核心改动域**：`backend/app/services/ai_service.py`（resolve_published_at 注入新 fallback + sources_from_citations 标 method）+ 新建 `backend/app/services/meta_time_service.py`（解析入口 + Redis cache + Semaphore）+ alembic migration（加列）+ pytest 4 条 + 一次性脚本。

## Technical Context

**Language/Version**: Python 3.9（沿用既有 backend venv）

**Primary Dependencies**:
- 既有：FastAPI, SQLAlchemy 2.x, asyncpg, `redis.asyncio`, httpx (spec-006 引入), alembic
- **新增**：无（HTML 解析用 stdlib `re`）

**Storage**: PostgreSQL 16（既有，加一列）+ Redis 7（既有，新增 namespace `meta_time:`）

**Testing**: pytest + pytest-asyncio + pytest-httpx（既有；用 httpx_mock fixture mock HTTP 响应）

**Target Platform**: 后端单 uvicorn 进程；本地 venv 启动；阿里云部署直接复用同代码

**Project Type**: Single-project web-service（既有 `backend/`）

**Performance Goals**:
- 单次 meta 解析 P95 ≤ 3s / P99 ≤ 6s
- 缓存命中 ≤ 100ms
- 单次搜索 E2E 延迟增加 ≤ 5s（5 并发 × 1s 平均）

**Constraints**:
- HTTP 并发硬上限 = 5（asyncio.Semaphore 全局）
- 单次 GET timeout = 5s
- HTML 体积上限读 256KB（避免内存爆炸）
- 时间合理性区间：`[2010-01-01, now + 1day]`
- 不引入新外部服务、不引入 BeautifulSoup（用 stdlib re）

**Scale/Scope**: 单实例后端；演示规模 10 并发用户；DB 现存 232 条候选一次性脚本运行

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

`.specify/memory/constitution.md` 仍是空模板。**默认通过**。沿用 CLAUDE.md 5 条软性约束 + 4 件套测试约定。

**Phase 0 后再检查**：✅ 通过。
**Phase 1 后再检查**：✅ 通过。

## Project Structure

### Documentation (this feature)

```text
specs/007-meta-time-fallback/
├── plan.md              # 本文件
├── research.md          # Phase 0：5 个技术决策
├── data-model.md        # Phase 1：MetaTimeResult + Source 增量 + Redis schema
├── quickstart.md        # Phase 1：本地跑通 + 回灌脚本运行说明
├── contracts/
│   └── meta_time_service.md
└── tasks.md             # Phase 2 输出
```

### Source Code (repository root)

```text
backend/
├── app/
│   ├── models/
│   │   └── source.py                  # ⚙️ 新增 source_time_method 列
│   ├── services/
│   │   ├── ai_service.py              # ⚙️ resolve_published_at 注入 meta fallback；
│   │   │                              #    sources_from_citations 写 source_time_method
│   │   ├── meta_time_service.py       # 🆕 resolve_meta_published_at() 入口 +
│   │   │                              #    Redis cache + Semaphore + 5 meta 标签匹配
│   │   └── cache.py                   # ⚙️ 加 meta_time_cache_key() 辅助
│   └── ...
├── alembic/versions/
│   └── 0004_add_source_time_method.py # 🆕 migration
├── scripts/
│   └── backfill_meta_time.py          # 🆕 一次性回灌脚本
└── tests/
    ├── test_meta_time_service.py      # 🆕 4 条 pytest
    └── fixtures/
        └── meta_time_smzdm_sample.html # 🆕 mock HTML fixture
```

**Structure Decision**: 沿用 `backend/` 单体。`meta_time_service.py` 与 `deep_fetch_service.py` 并列同层（都是"信源增强"类服务，职责不重叠：meta 只读 head meta，deep_fetch 渲染整页）。不复用 fetchers/ 子包 —— 那里是 Playwright 浏览器抽象，meta_time 用纯 httpx，两条独立路径更清晰。

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| —         | —          | —                                   |
