# Implementation Plan: 微头条话题页单帖深度抓取（Phase 1）

**Branch**: `006-deep-fetch-toutiao` | **Date**: 2026-05-20 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `specs/006-deep-fetch-toutiao/spec.md`

## Summary

给定一个被识别为「微头条话题页」的信源 URL + 用户搜索关键词，后端用 Playwright 渲染抓取页内单帖列表，用现有 Ark Seed 2.0 provider 对候选单帖打分，返回 Top 1 命中的 permalink；命中后替换信源 URL 并把原话题页存入 `places.topic_url_original`；失败时（超时/无匹配/相关性低于阈值/抓取出错）从信源 chip 列表整体剔除该话题页，对应点位标记 `location_confidence=low` 让 spec-004 过滤层兜底。Redis 缓存深抓结果 24h；并发限流双层（per-request ≤ 2 + process-global ≤ 3）。

**核心改动域**：`backend/app/services/`（新增 `deep_fetch_service.py`）+ `backend/app/services/ai_service.py`（信源后处理钩子）+ `backend/app/models/place.py`（新增字段）+ alembic migration + pytest 2 条。

## Technical Context

**Language/Version**: Python 3.11（沿用现有 backend venv）

**Primary Dependencies**:
- 既有：FastAPI, SQLAlchemy 2.x, asyncpg, Redis client (`redis.asyncio`), `volcengine-python-sdk[ark]`（已用）, alembic
- **新增**：`playwright>=1.40`（Python 异步版） + `playwright install chromium`

**Storage**: PostgreSQL 16 + PostGIS（既有，加一列） / Redis 7（既有，新增缓存 namespace `deep_fetch:`）

**Testing**: pytest + pytest-asyncio（既有）；新增依赖注入边界让 FakeFetcher 可替换真实 Playwright

**Target Platform**: 后端单 uvicorn 进程，本地 venv 启动；后续阿里云部署需额外 `playwright install --with-deps chromium`

**Project Type**: Single-project web-service（既有 `backend/` 单体）

**Performance Goals**:
- 单次深抓 P95 ≤ 20s / P99 ≤ 30s（含超时触发）
- 缓存命中 ≤ 100ms
- E2E 搜索延迟 P95 增加 ≤ 10s

**Constraints**:
- 进程内 Playwright 并发硬上限 = 3（asyncio.Semaphore 全局）
- 单请求内并发深抓 = 2（per-request Semaphore）
- 单次渲染 timeout = 15s
- LLM 评分单次 timeout = 5s（fail-fast 降级到关键词字面匹配）
- 不引入新外部服务（OSS / 独立爬虫微服务 → Phase 3）

**Scale/Scope**: 单实例后端，演示规模（10 并发用户量级）；本期不考虑多实例水平扩展。

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

项目 `.specify/memory/constitution.md` 当前是空模板（未定义自定义原则）。**默认通过**，无 gate 违例。复用项目级 CLAUDE.md 的 5 条协作规则作为软性约束：所有技术决策可被「编程小白可懂的大白话」解释；新功能配 happy-path + regression 测试。

**Phase 0 后再检查**：✅ 通过（research.md 未引入新原则违例）。

**Phase 1 后再检查**：✅ 通过（data-model.md / contracts 都保持单体边界，未引入新服务）。

## Project Structure

### Documentation (this feature)

```text
specs/006-deep-fetch-toutiao/
├── plan.md              # 本文件
├── research.md          # Phase 0：Playwright vs alternatives, 缓存 key 设计, 相关性阈值
├── data-model.md        # Phase 1：TopicPagePost / DeepFetchResult / Place schema delta
├── quickstart.md        # Phase 1：本地跑通 5 步（含 playwright install）
├── contracts/
│   └── deep_fetch_service.md   # 内部服务接口（Python protocol）
└── tasks.md             # Phase 2 输出（/speckit-tasks 阶段生成）
```

### Source Code (repository root)

```text
backend/
├── app/
│   ├── models/
│   │   └── place.py                # ⚙️ 新增 topic_url_original 列
│   ├── services/
│   │   ├── ai_service.py           # ⚙️ 钩入 deep_fetch 后处理；扩展 is_topic_aggregator_url 返回元组（is_topic, platform）
│   │   ├── deep_fetch_service.py   # 🆕 入口 + 编排 + 限流 + 缓存
│   │   ├── fetchers/
│   │   │   ├── __init__.py
│   │   │   ├── base.py             # 🆕 Protocol: PostFetcher
│   │   │   ├── toutiao_fetcher.py  # 🆕 Playwright 实现
│   │   │   └── fake_fetcher.py     # 🆕 pytest 用
│   │   └── cache.py                # ⚙️ 复用，加 deep_fetch namespace 辅助
│   └── routers/
│       └── search.py               # ⚙️ 信源 chip 列表整体剔除失败话题页
├── alembic/versions/
│   └── 006_add_topic_url_original.py   # 🆕 migration
└── tests/
    ├── test_deep_fetch_service.py  # 🆕 2 条 pytest（happy + timeout regression）
    └── fixtures/
        └── toutiao_topic_page.json # 🆕 mock 渲染输出 fixture
```

**Structure Decision**: 沿用既有 `backend/` 单体 web-service 结构；新建 `services/fetchers/` 子目录隔离爬虫层，便于 Phase 2 扩展知乎/小红书新 fetcher 时复用 `PostFetcher` protocol。无需 contracts/ 目录的外部 API 规范——本能力是后端内部模块，对前端的契约延续既有 `/api/v1/search` 响应（仅信源 URL 内容变化，schema 不变）。

## Complexity Tracking

> Constitution Check 通过，本节空着即可。

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| —         | —          | —                                   |
