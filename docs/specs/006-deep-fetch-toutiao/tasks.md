---

description: "Task list for spec-006 微头条话题页单帖深度抓取（Phase 1）"
---

# Tasks: 微头条话题页单帖深度抓取（Phase 1）

**Input**: Design documents from `specs/006-deep-fetch-toutiao/`

**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/deep_fetch_service.md ✅, quickstart.md ✅

**Tests**: 本 spec 显式要求 2 条 pytest（FR-011 / spec 验收标准 #5）—— happy-path + timeout regression。包含。

**Organization**: 按 user story 分阶段。US1 = MVP（命中替换）；US2 = 安全降级；US3 = 可观测性。

## Format: `[ID] [P?] [Story] Description`

- **[P]**: 不同文件、无依赖，可并行
- **[Story]**: US1 / US2 / US3 对应 spec.md 的 user stories
- 所有路径相对 repo root

## Path Conventions

- Backend: `backend/app/` + `backend/tests/`
- Migrations: `backend/alembic/versions/`

---

## Phase 1: Setup（共享基础设施）

**Purpose**: 装新依赖、起浏览器

- [X] T001 在 venv 装 Playwright Python SDK：执行 `/Users/yihan_guo/Desktop/异想天开/旅居产品_副本/.venv/bin/python -m pip install "playwright>=1.40"`，并把 `playwright>=1.40` 加进 `backend/requirements.txt`
- [X] T002 装 Chromium 浏览器：执行 `/Users/yihan_guo/Desktop/异想天开/旅居产品_副本/.venv/bin/python -m playwright install chromium`（约 200MB，3-5 分钟）
- [X] T003 [P] 在 `backend/app/config.py` 增加 3 个 env 配置项：`DEEP_FETCH_RELEVANCE_THRESHOLD`（默认 0.6）、`DEEP_FETCH_TIMEOUT_SECONDS`（默认 15.0）、`DEEP_FETCH_GLOBAL_CONCURRENCY`（默认 3）

---

## Phase 2: Foundational（所有 user story 的阻塞前置）

**Purpose**: 数据库列、缓存命名空间、Protocol 抽象——必须先完成这些，才能写 service 业务

**⚠️ CRITICAL**: 阻塞所有 user story

- [X] T004 [P] 创建 Alembic migration `backend/alembic/versions/0003_add_topic_url_original.py`（注：编号沿用既有 0001/0002 体系而非 006_）：`ALTER TABLE places ADD COLUMN topic_url_original TEXT NULL`；回滚 DROP COLUMN
- [X] T005 [P] 在 `backend/app/models/place.py` 的 Place 模型加 `topic_url_original: Mapped[str | None] = mapped_column(Text, nullable=True)` 字段
- [X] T006 [P] 创建 `backend/app/services/fetchers/__init__.py` + `backend/app/services/fetchers/base.py`：定义 `TopicPagePost` dataclass + `PostFetcher` Protocol + `FetcherError` 异常类（按 contracts/deep_fetch_service.md §2）
- [X] T007 在 `backend/app/services/cache.py` 加 `deep_fetch_cache_key(url, keyword) -> str` 辅助函数（md5 哈希，带 `deep_fetch:v1:` 前缀）；不破坏既有 cache 模块
- [X] T008 跑 migration 验证落地：`cd backend && /Users/yihan_guo/Desktop/异想天开/旅居产品_副本/.venv/bin/python -m alembic upgrade head`，并用 `psql` 或 `\d places` 确认新列存在

**Checkpoint**: 基础设施就绪 —— 三个 user story 可以并行启动

---

## Phase 3: User Story 1 - 话题页信源自动落到具体单帖（Priority: P1）🎯 MVP

**Goal**: 给定话题页 URL + 关键词，返回最相关的具体单帖 permalink；落库时 source_url 用单帖 URL，topic_url_original 存原话题页

**Independent Test**: pytest mock FakeFetcher 返回 5 条 mock 帖（3 条含「莫干山」、2 条无关），调用 `fetch_and_match("https://weitoutiao.zjurl.cn/topic/xxx", "莫干山")`，断言返回 `match_status="matched"` + matched_post.title 含「莫干山」 + score ≥ 0.6

### Tests for User Story 1（spec 显式要求）⚠️

> 先写 fixture + 测试骨架，让测试 fail，再补实现

- [X] T009 [P] [US1] 创建 `backend/tests/fixtures/toutiao_topic_page.json`：5 条 mock 帖结构（title/text_excerpt/published_at/permalink_url 四字段），3 条含「莫干山」相关内容、2 条无关
- [X] T010 [P] [US1] 创建 `backend/tests/test_deep_fetch_service.py` 骨架 + `FakeFetcher` 实现类（在测试文件内）+ `test_deep_fetch_happy_path` 测试：从 fixture 加载 → 调用 fetch_and_match → 断言 matched + 命中预期帖子

### Implementation for User Story 1

- [X] T011 [P] [US1] 在 `backend/app/services/fetchers/toutiao_fetcher.py` 实现 `ToutiaoPlaywrightFetcher(PostFetcher)`：用 playwright async API 启动 chromium、goto URL、等待选择器、抽取帖子列表的 4 字段，返回 `list[TopicPagePost]`；异常包装为 FetcherError；遵守 contracts/deep_fetch_service.md §2 契约
- [X] T012 [US1] 在 `backend/app/services/deep_fetch_service.py` 实现 `DeepFetchResult` Pydantic 模型（按 data-model.md §实体 2 的字段定义，含 `match_status` 字面量枚举）
- [X] T013 [US1] 在 `backend/app/services/deep_fetch_service.py` 实现 `pick_top_relevant(posts, keyword, threshold)` 函数：L1 字面匹配过滤 + L2 单帖直返 / Ark LLM 评分 + JSON 解析护栏 + fallback 到 keyword_only；返回 `(matched_post?, top_score, status, fallback_mode)`（按 contracts §3）
- [X] T014 [US1] 在 `backend/app/services/deep_fetch_service.py` 实现 `fetch_and_match(url, keyword, *, fetcher=None)` 主入口：Redis 缓存查询 → 命中返回 → 未命中走 fetcher + scorer → 组装 DeepFetchResult → SETEX 24h（按 contracts §1）；进程级 `asyncio.Semaphore(3)` 作为模块级单例
- [X] T015 [US1] 在 `backend/app/services/ai_service.py`（不在 routers/search.py，因为 ai_search_pipeline_stream 在这里）加 `_apply_deep_fetch_to_sources(sources, query)`：用 per-request `asyncio.Semaphore(2)` 包裹，对话题页 source 并发调 `fetch_and_match`；命中替换 url + 落 _topic_url_original 标记；**直接做整体剔除（FR-013）**，无 placeholder
- [X] T016 [US1] 在 `normalize_candidates` 透传 `_topic_url_original` 到 spot 字典，在 `upsert_ai_places` 把 spot._topic_url_original 写到 places.topic_url_original

**Checkpoint**: US1 完成 —— 命中场景跑通；pytest happy-path 应该通过

---

## Phase 4: User Story 2 - 抓不到相关单帖时安全降级（Priority: P1）

**Goal**: 失败的话题页 source 整体剔除（不出现在 chip 列表也不出现在地图），对应 places 标记 location_confidence=low

**Independent Test**: pytest mock FakeFetcher 抛 asyncio.TimeoutError，调用 `fetch_and_match`，断言返回 `match_status="timeout"` 且无异常抛出；router 层集成测试断言 timeout 信源不在响应 sources[] 里

### Tests for User Story 2 ⚠️

- [X] T017 [P] [US2] 在 `backend/tests/test_deep_fetch_service.py` 加 `test_deep_fetch_timeout_fallback` 测试：FakeFetcher 抛 TimeoutError → 断言 `match_status="timeout"` + `matched_post=None` + 不抛异常
- [X] T018 [P] [US2] 在同测试文件加 `test_deep_fetch_no_match` 测试：FakeFetcher 返回 5 条全部不含关键词的帖 → 断言 `match_status="no_match"` + `top_score < threshold`

### Implementation for User Story 2

- [X] T019 [US2] 在 `deep_fetch_service.fetch_and_match` 内补齐错误处理路径：`asyncio.TimeoutError` → `match_status=timeout` + `matched_post=None`；`FetcherError` / 其它异常 → `match_status=error`；统一记录 `duration_ms`；所有错误路径**都进入缓存**（避免坏话题页被反复抓）
- [X] T020 [US2] 已在 Phase 3 T015 中直接实现（_apply_deep_fetch_to_sources 内对非 matched 整体剔除），无需 placeholder 替换
- [X] T021 [US2] **被剔除路径自动满足**：失败的话题页 source 在 _apply_deep_fetch_to_sources 中被剔除，对应的 place 根本不会被 LLM 引用 → 不会进入 places 表 → 无需再标记 location_confidence=low（结果一致，路径更干净）

**Checkpoint**: US1 + US2 都完整 —— pytest 3 条全部绿；冒烟测试场景下失败信源整体不出现在用户视野

---

## Phase 5: User Story 3 - 深抓延迟可观测（Priority: P2）

**Goal**: 每次深抓输出结构化日志，含 url/duration_ms/posts_extracted/match_status/top_score/cache_hit/fallback_mode

**Independent Test**: 跑一次包含话题页的搜索，从 stderr 抓 stdout 行 `{"event": "deep_fetch.completed", ...}`，确认 7 个字段齐全

### Implementation for User Story 3

- [X] T022 [US3] 在 `deep_fetch_service.fetch_and_match` 函数末尾（成功 + 失败 + 缓存命中三个出口都覆盖），用 `logging.getLogger("deep_fetch").info(json.dumps({...}))` 输出按 contracts §5 格式的结构化日志（`_log_completed()` 函数实现，3 个出口都调用）
- [X] T023 [US3] 检查 main.py 日志配置——确认现有 logging 不会吞 INFO 级别（用 `print` 测试可见即可）

**Checkpoint**: 三个 user story 完整 —— 演示就绪

---

## Phase 6: Polish & 跨切关注

- [X] T024 [P] 把 `playwright>=1.40` 写入 `backend/requirements.txt`（Phase 1 已做）
- [X] T025 [P] 在 `backend/README.md` 加部署提示（见下方 commit）
- [X] T026 跑全套 pytest：49 既有 + 8 新增 = 57 全过（含 happy / timeout / no_match / error / cache_hit / 3 单元测试）
- [ ] T027 跑 quickstart.md 的 6 步人工冒烟：含真实搜索 + DB 抽查 + 缓存命中验证 + SC-001 10 条样本抽查表填写 —— **需用户操作**

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1（Setup）**：无依赖，T001 → T002 顺序，T003 可并行
- **Phase 2（Foundational）**：依赖 Phase 1；T004/T005/T006 [P] 可并行，T007 独立，T008 在 T004 + T005 完成后跑
- **Phase 3（US1 MVP）**：依赖 Phase 2 完成；内部顺序：T009/T010 [P] → T011/T012 [P] → T013 → T014 → T015 → T016
- **Phase 4（US2 降级）**：依赖 Phase 2；US1 的 T014/T015 完成后可启动；T017/T018 [P] → T019 → T020 → T021
- **Phase 5（US3 可观测）**：依赖 T014 完成；T022 → T023
- **Phase 6（Polish）**：依赖前面所有 story 完成

### User Story Dependencies

- **US1（P1 MVP）**：Phase 2 完成后即可启动；产出可独立测试的 happy-path
- **US2（P1）**：可与 US1 并行写测试（T017/T018），但 T019/T020/T021 需要 US1 的 T014/T015 完成后才能补
- **US3（P2）**：依赖 US1 的 T014 主入口存在；纯加日志，最后做最稳

### Within Each User Story

- 测试先于实现（spec 显式要求 TDD 风格）
- 实体（models/dataclass）先于服务（service）
- 服务先于路由（router）

### Parallel Opportunities

- T003 [P]、T004 [P] [P] T005 [P] [P] T006 [P] 可并行（不同文件）
- T009 [P] [P] T010 [P]、T011 [P]（fixture + 骨架 + Playwright 实现并行）
- T017 [P] [P] T018 [P]（两条 regression 测试并行写）
- T024 [P] [P] T025 [P]（文档与 requirements 并行）

---

## Parallel Example: User Story 1 启动时

```bash
# 同时启动（不同文件，互不依赖）：
Task: "T009 创建 toutiao_topic_page.json fixture"
Task: "T010 写 test_deep_fetch_happy_path 测试骨架 + FakeFetcher"
Task: "T011 实现 ToutiaoPlaywrightFetcher"
```

---

## Implementation Strategy

### MVP First（仅 User Story 1）

1. 完成 Phase 1（Setup）+ Phase 2（Foundational）
2. 完成 Phase 3（US1）—— 命中场景跑通
3. **暂停验证**：用 quickstart.md 第 4 步冒烟，确认命中路径正常
4. （此时尚未做 US2 剔除逻辑，失败的话题页仍会以原 URL 留在 sources 里——可接受的中间态）

### 增量交付

1. Setup + Foundational → 基础就绪
2. 加 US1 → 命中场景可演示（MVP demo 可用）
3. 加 US2 → 失败安全降级（产品承诺达标）
4. 加 US3 → 日志可观测（运维就绪）
5. Polish → 文档 + 全套 pytest + 人工抽查（上线就绪）

### 风险点

- T002（Chromium 装包）耗时长，建议在 Phase 1 一启动就并行下载，别等到 T011 才发现没装
- T011（Playwright 抽取选择器）依赖微头条 SPA 结构稳定，可能要先手动开浏览器 inspect 元素；可考虑先用 `page.content()` 落地一份 HTML 反推选择器
- T013 的 LLM JSON 校验是防幻觉关键，建议跑通最后用真实 Ark 调用做一次手动 smoke test

---

## Notes

- 所有 [P] 任务 = 不同文件、无依赖
- 每完成一个 task 立即 commit（项目有 pre-commit hook 跑 pytest，注意 hook 失败要立即修而不是 --no-verify）
- 每个 checkpoint 停下来人工验证一次，不要从 T001 一路冲到 T027
- 不允许跨 story 依赖打破独立性（US2 的剔除逻辑必须用同样的 fetch_and_match 入口）
