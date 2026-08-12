---
description: "Tasks for 002-fix-source-date"
---

# Tasks: 信源发布时间显示准确性修复

**Prerequisites**: spec.md ✅, plan.md ✅
**Tests**: ✅ Required（修 bug 必加 regression test，4 件套规则 3）

## Format: `[ID] [P?] [Story] Description`

---

- [ ] **T001** [US1] 写 `test_extract_date_from_url`（5 个用例，先 fail）
  - 文件：`backend/tests/test_ai_pipeline_mock.py`（append）
  - 用例：
    - `/n/2024/1108/c-xxx` → 2024-11-08
    - `/a/20260512A04QJ500` → 2026-05-12
    - `/2024/11/08/news.html` → 2024-11-08
    - `/news/2024-11-08/xxx` → 2024-11-08
    - `/no-date-here/xxx` → None
  - 跑：失败（函数还没实现）

- [ ] **T002** [US1] 实现 `extract_date_from_url(url) -> datetime | None`
  - 文件：`backend/app/services/ai_service.py`（在 `parse_source_date` 附近）
  - 正则要求月日齐全
  - 跑：T001 pass

- [ ] **T003** [US1] 写 `test_source_date_priority`（3 个 fallback 优先级用例，先 fail）
  - 文件：`backend/tests/test_ai_pipeline_mock.py`（append）
  - 用例：
    - URL 有日期 + citation 也有日期不同 → 取 URL
    - URL 无日期 + citation 有 → 取 citation
    - URL 无日期 + citation 无 + snippet 有 → 取 snippet
  - 跑：失败

- [ ] **T004** [US1/US2/US3] 改 build_sources 流程（line 539 附近 + line 313 附近）
  - 文件：`backend/app/services/ai_service.py`
  - line 539 那个分支：`date = extract_date_from_url(url) or parse_source_date(citation.published_at or citation.updated_at) or parse_source_date(snippet)`
  - 跑：T003 pass

- [ ] **T005** 跑全量 pytest 验证 0 回归
  - 期望：30 passed（21 老 + 8 spec 001 + 1 key prio + 0 spec 002 新加之外的）
  - 实际：30 + 5 新 = 35 passed

- [ ] **T006** commit + 触发 pre-commit 13 道关卡
  - commit message：`FIX(spec-002): 信源日期取 URL 路径优先 (Bug 3)`

## 完成标准

| SC | 验证方式 |
|---|---|
| SC-001 人民网 URL 日期 100% 准 | T001 + T002 |
| SC-002 提炼 vs 卡片一致 | 浏览器实测（手动） |
| SC-003 5 条 regression test | T001 + T003 |
| SC-004 0 回归 | T005 全量 pytest |
| SC-005 浏览器验证柚子营地 = 2024-11-08 | 实测 |
