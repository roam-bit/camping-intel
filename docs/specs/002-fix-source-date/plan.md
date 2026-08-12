# Implementation Plan: 信源发布时间显示准确性修复

**Branch**: `main`（spec 002 直接进 main，bug 修复体量小）| **Date**: 2026-05-18 | **Spec**: [spec.md](./spec.md)

## Summary

`backend/app/services/ai_service.py` 改 2 个函数 + 加 1 个工具函数：
1. **新增 `extract_date_from_url(url)`** —— 用正则识别常见 URL 路径里的发布日期模式
2. **改 `parse_source_date(value)`** —— 加 URL 路径识别（FR-001）
3. **改 build_sources 流程**（line 539 附近）—— published_at 优先级改为：URL > citation.published_at > snippet（FR-002）

预计代码改动：**1 个文件，约 40 行**，TDD 严格执行。

## Technical Context

- Language: Python 3.9 backend
- 涉及文件：`backend/app/services/ai_service.py`（核心）+ `backend/tests/test_ai_pipeline_mock.py`（测试 append）
- 不动：前端 / 数据库 / 配置 / API 签名

## Architecture

只动 1 个 backend 文件。

### 改动前数据流（bug）

```
Ark search 返回 citation
  ↓
build_sources():
  date = parse_source_date(citation.published_at or citation.updated_at or snippet)
                            ^^^^^^^^^^^^^^^^^^^^^                       ^^^^^^^
                            可能是索引时间                          可能有错的"2026-04-22"
```

### 改动后数据流

```
Ark search 返回 citation
  ↓
build_sources():
  date = (
    extract_date_from_url(citation.url)   # 1️⃣ URL 抽（最准）
    or parse_source_date(citation.published_at or citation.updated_at)   # 2️⃣ citation
    or parse_source_date(snippet)         # 3️⃣ snippet（fallback）
  )
```

### URL 日期模式（FR-001）

正则覆盖：
- `/n/2024/1108/` （人民网）
- `/a/20260512A04QJ500` （腾讯新闻）
- `/2024/11/08/` （搜狐 / 新浪）
- `/news/2024-11-08/` （部分地方党报）

## Tasks

按 TDD 流程：

- [ ] **T001**：写测试 `test_extract_date_from_url`（4 个 URL 模式 + 1 个无日期），先 fail
- [ ] **T002**：实现 `extract_date_from_url(url) -> datetime | None`，使 T001 pass
- [ ] **T003**：写测试 `test_parse_source_date_priority`（URL vs citation vs snippet 优先级），先 fail
- [ ] **T004**：改 build_sources / `attach_answer_dates_to_sources` 流程使 T003 pass
- [ ] **T005**：跑全量 pytest 确认 0 regression
- [ ] **T006**：commit（触发 pre-commit 13 道关卡）

## Risks

| 风险 | 缓解 |
|---|---|
| URL 正则误识别（如把分类路径 `/2024-class/` 当日期）| 正则要求**月日齐全**（`/YYYY/MM/DD` 或 `/YYYYMMDD`），分类路径不匹配 |
| 旧 source 已存错日期 | 不回填（spec 决策 Q3）；下次 AI 重抽自然刷新 |
| Ark citation.published_at 偶尔比 URL 更准 | 不在本次范围（spec 决策 Q2 信 URL）；未来 Q4 评估再说 |

## Rollback

`git revert` 单 commit，不动 DB。

## Constitution Check

跳过（项目 constitution 仍未填）；遵守 CLAUDE.md 「开发工作流」即可（含 4 件套）。

可以进入 implement 阶段。
