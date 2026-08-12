---

description: "Task list for spec-007 信源发布时间 HTML meta fallback"
---

# Tasks: 信源发布时间 HTML meta fallback

**Input**: Design documents from `specs/007-meta-time-fallback/`

**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/meta_time_service.md ✅, quickstart.md ✅

**Tests**: spec 显式要求 4 条 pytest（spec 验收标准 #5 / FR-012）。包含。

**Organization**: 按 user story 分阶段。US1 = meta 解析核心（MVP）；US2 = 安全降级；US3 = 历史回灌；US4 = 可观测。

## Format: `[ID] [P?] [Story] Description`

- **[P]**: 不同文件、无依赖，可并行
- **[Story]**: US1 / US2 / US3 / US4 对应 spec.md user stories
- 所有路径相对 repo root

## Path Conventions

- Backend: `backend/app/` + `backend/tests/` + `backend/scripts/`
- Migrations: `backend/alembic/versions/`

---

## Phase 1: Setup（共享基础设施）

**Purpose**: 配置项（无新依赖，httpx 已由 spec-006 引入）

- [X] T001 [P] 在 `backend/app/config.py` 增加 3 个 env 配置项：`META_TIME_HTTP_TIMEOUT`（默认 5.0）、`META_TIME_HTTP_CONCURRENCY`（默认 5）、`META_TIME_HTML_MAX_BYTES`（默认 262144 = 256KB）

---

## Phase 2: Foundational（所有 user story 的阻塞前置）

**Purpose**: DB 列、缓存 key helper —— 必须先完成

**⚠️ CRITICAL**: 阻塞所有 user story

- [X] T002 [P] 创建 Alembic migration `backend/alembic/versions/0004_add_source_time_method.py`：`ALTER TABLE sources ADD COLUMN source_time_method VARCHAR(40) NULL`；回滚 DROP COLUMN
- [X] T003 [P] 在 `backend/app/models/source.py` 的 Source 模型加 `source_time_method: Mapped[str | None] = mapped_column(String(40), nullable=True)` 字段
- [X] T004 [P] 在 `backend/app/services/cache.py` 加 `meta_time_cache_key(url) -> str` 辅助函数（md5 哈希，带 `meta_time:v1:` 前缀）；`_redis_key` 已支持 `deep_fetch:` 前缀的独立 namespace，同样放行 `meta_time:`
- [X] T005 跑 migration 验证：`cd backend && <venv>/bin/python -m alembic upgrade head`，用 `\d sources` 确认新列存在

**Checkpoint**: 基础设施就绪 —— 四个 user story 可并行启动

---

## Phase 3: User Story 1 - 信源发布时间真实可信（Priority: P1）🎯 MVP

**Goal**: 给定 URL 路径无日期的信源 URL，从 HTML meta 标签抽真实发布时间，注入 resolve_published_at fallback 链

**Independent Test**: pytest 用 httpx_mock 喂一个含 `og:published_time` 的 smzdm fixture HTML，调用 `resolve_meta_published_at(url)` → 断言 status=matched + published_at 正确 + source_tag

### Tests for User Story 1（spec 显式要求）⚠️

- [X] T006 [P] [US1] 创建 `backend/tests/fixtures/meta_time_smzdm_sample.html`：模拟 smzdm 文章页 `<head>`，含 `<meta property="article:published_time" content="2026-03-15T15:41:00+08:00">`
- [X] T007 [P] [US1] 在 `backend/tests/test_meta_time_service.py` 写 `test_meta_smzdm_happy_path`：httpx_mock 返回 fixture → 调 resolve_meta_published_at → 断言 matched + 2026-03-15 + source_tag=article:published_time

### Implementation for User Story 1

- [X] T008 [US1] 在 `backend/app/services/meta_time_service.py` 实现 `MetaTimeResult` Pydantic 模型（按 data-model.md §实体 1）+ `MetaTimeStatus` / `MetaSourceTag` Literal 类型
- [X] T009 [US1] 在同文件实现 `_META_PATTERNS`（5 个 meta 标签的编译正则，按 contracts §4）+ `_parse_meta_time_value()`（ISO/中文/通用日期宽松解析，contracts §5）+ `_is_valid_publish_time()`（[2010, now+1d] 校验，contracts §6）
- [X] T010 [US1] 在同文件实现 `resolve_meta_published_at(url, *, http_client=None, timeout_seconds=5.0)` 主入口：Redis 缓存查询 → 命中返回 → 未命中走 Semaphore(5) + httpx GET（限 256KB）+ 正则匹配 + 时间校验 → 组装 MetaTimeResult → SETEX 24h（按 contracts §1）
- [X] T011 [US1] 改造 `backend/app/services/ai_service.py` 的 `resolve_published_at`：返回值从 `datetime | None` 改为 `tuple[datetime | None, str | None]`（datetime + method）；在 URL 路径解析失败后、citation 之前插入 `await resolve_meta_published_at(url)` 调用（按 contracts §3）
- [X] T012 [US1] 改造 `sources_from_citations`：消费 resolve_published_at 新返回的 (date, method)，把 method 写入 source dict 的 `source_time_method` 字段
- [X] T013 [US1] 改造 `upsert_ai_places`（写 Source 模型处）：把 source dict 的 `source_time_method` 写入 `Source.source_time_method` 列

**Checkpoint**: US1 完成 —— meta 解析跑通；happy-path pytest 通过

---

## Phase 4: User Story 2 - 抓不到 meta 时安全降级（Priority: P1）

**Goal**: HTTP 超时 / 4xx5xx / 无 meta / 解析异常 → 返回 None + 对应 status，不抛错，回退原 fallback 链

**Independent Test**: pytest 用 httpx_mock 构造 timeout / 404 / 无 meta / 非法时间 四个场景，断言每个都返回 None 且不抛异常

### Tests for User Story 2 ⚠️

- [X] T014 [P] [US2] 在 `test_meta_time_service.py` 加 `test_meta_no_tag_fallback`：httpx_mock 返回无任何 meta 标签的 HTML → 断言 status=no_meta + published_at=None
- [X] T015 [P] [US2] 加 `test_meta_timeout_fallback`：httpx_mock 抛 TimeoutException → 断言 status=timeout + 不抛异常
- [X] T016 [P] [US2] 加 `test_meta_invalid_time_rejected`：fixture HTML 里 meta 是 `2099-01-01` → 断言 FR-006 拒绝 → status=no_meta（不接受未来时间）

### Implementation for User Story 2

- [X] T017 [US2] 在 `resolve_meta_published_at` 内补齐错误处理：`httpx.TimeoutException` → status=timeout；HTTP 4xx/5xx → status=http_error；无 meta / 时间非法 → status=no_meta；其它异常 → status=error；所有失败结果**都进缓存**（避免反复抓死站）
- [X] T018 [US2] 验证 `resolve_published_at` 在 meta 返回非 matched 时正确回退到 citation → snippet（不破坏 spec-002 原行为）—— 此为代码审查任务，确认 contracts §3 的 if 链顺序正确

**Checkpoint**: US1 + US2 完成 —— 4 条核心 pytest 全绿

---

## Phase 5: User Story 3 - 历史脏数据回灌修正（Priority: P2）

**Goal**: 一次性脚本扫 DB 232 条候选源，重抽 meta 真实日期并 UPDATE

**Independent Test**: 在测试 DB 跑脚本（或 dry-run 模式），确认扫描计数、并发限流、UPDATE 逻辑、统计报告都正确

### Implementation for User Story 3

- [X] T019 [US3] 创建 `backend/scripts/backfill_meta_time.py`：独立连 DB（SQLAlchemy session）→ SELECT 候选行（`source_time_method IN ('citation','snippet') OR IS NULL` + URL 无日期段）→ 按 URL 去重 → asyncio.gather + Semaphore(5) 调 `resolve_meta_published_at` → matched 的 UPDATE source_time + source_time_method，其它仅 UPDATE method（保留 source_time）→ 输出扫描/成功/跳过/失败统计 + 域名级成功率（按 data-model.md §回灌脚本数据流）
- [X] T020 [US3] 给脚本加 `--dry-run` 开关：只打印将要做的 UPDATE，不实际写库（便于先验证再正式跑）

**Checkpoint**: US3 完成 —— 回灌脚本可运行（实际跑放 Phase 7 验证阶段）

---

## Phase 6: User Story 4 - 性能可观测（Priority: P3）

**Goal**: 每次 meta 解析输出结构化日志

**Independent Test**: 跑一次含 smzdm 信源的搜索，stderr 有 `meta_time.resolved` 日志含 6 字段

### Implementation for User Story 4

- [X] T021 [US4] 在 `resolve_meta_published_at` 三个出口（成功 / 失败 / 缓存命中）都加 `logging.getLogger("meta_time").info("meta_time.resolved", extra={...})`，字段按 contracts §7：url / status / source_tag / published_at / duration_ms / cache_hit

**Checkpoint**: 四个 user story 完整

---

## Phase 7: Polish & 验证

- [X] T022 跑全套 pytest：`cd backend && <venv>/bin/python -m pytest`；确认 64 既有 + 4 新 = 68 全绿，无回归（重点看 spec-002 的 test_ai_pipeline 信源时间测试没被 resolve_published_at 签名变更打挂）
- [X] T023 真实跑回灌脚本 `backfill_meta_time.py`（先 --dry-run 看计划，再正式跑）；记录成功率，抽样 10 条与原网页 og:published_time 对比验证 SC-004
- [ ] T024 [P] 跑 quickstart.md 的真实搜索冒烟 + 缓存命中验证

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1（Setup）**：无依赖
- **Phase 2（Foundational）**：依赖 Phase 1；T002/T003/T004 [P] 可并行，T005 在 T002+T003 后
- **Phase 3（US1 MVP）**：依赖 Phase 2；T006/T007 [P] → T008 → T009 → T010 → T011 → T012 → T013
- **Phase 4（US2）**：依赖 US1 的 T010/T011 完成；T014/T015/T016 [P] → T017 → T018
- **Phase 5（US3）**：依赖 US1 的 T010 完成（脚本复用 resolve_meta_published_at）
- **Phase 6（US4）**：依赖 US1 的 T010 完成
- **Phase 7（Polish）**：依赖前面所有 story

### 关键依赖链

- `resolve_published_at` 签名从 `→ datetime` 改成 `→ (datetime, method)`（T011）是**破坏性签名变更**，所有调用方都要同步改（T012 sources_from_citations / 还要排查别处）—— T022 全量 pytest 是这一步的安全网

### Parallel Opportunities

- T002 [P] / T003 [P] / T004 [P]（不同文件）
- T006 [P] / T007 [P]（fixture + 测试骨架）
- T014 [P] / T015 [P] / T016 [P]（三条降级测试）

---

## Parallel Example: User Story 1 启动时

```bash
Task: "T006 创建 meta_time_smzdm_sample.html fixture"
Task: "T007 写 test_meta_smzdm_happy_path"
```

---

## Implementation Strategy

### MVP First（US1）

1. Phase 1 + 2（Setup + Foundational）
2. Phase 3（US1）—— meta 解析核心跑通
3. **暂停验证**：happy-path pytest 通过

### 增量交付

1. Setup + Foundational → 基础就绪
2. US1 → meta 解析 + fallback 注入（核心价值）
3. US2 → 安全降级（产品承诺达标）
4. US3 → 历史回灌（清存量脏数据）
5. US4 → 可观测
6. Polish → 全量 pytest + 真实回灌 + 冒烟

### 风险点

- T011 改 `resolve_published_at` 签名是破坏性变更 —— 先全局 grep 所有调用方，T022 全量测试兜底
- meta 正则只做了正向属性顺序匹配（contracts §4 备注）—— 真实站点命中率不够时再补反向顺序正则
- 回灌脚本跑外网 HTTP —— 注意代理（CLAUDE.md 提到 FlClash 7890）

---

## Notes

- 每完成一个 task 立即 commit（pre-commit 会跑 pytest + ruff + tsc，hook 失败立即修不要 --no-verify）
- 每个 checkpoint 停下来人工验证
- 不允许跨 story 依赖打破独立性
