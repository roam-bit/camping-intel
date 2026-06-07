# Specification Quality Checklist: 搜索地理意图识别 amap geocoding 兜底

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-05-23
**Feature**: [spec.md](../spec.md)

## Content Quality

- [x] No implementation details (languages, frameworks, APIs)
  - 备注：spec 提到「amap geocoding API」「Redis」「places.py 的 geocode_query 函数」，这些是**已存在的系统组件名**，是用户需求里就明确指定要复用的 —— 不是「实现细节泄露」，而是「集成边界声明」。Out of Scope 章节也明确表示不引入新组件。
- [x] Focused on user value and business needs
  - User Story 1/2/3 都从用户视角描述（用户搜什么 → 期望看到什么）
- [x] Written for non-technical stakeholders
  - 主体描述用 PM 语言（"用户搜「景德镇」期望看到江西景德镇内容"），技术约束放在 Assumptions/Out of Scope
- [x] All mandatory sections completed
  - User Scenarios ✅ / Requirements ✅ / Success Criteria ✅

## Requirement Completeness

- [x] No [NEEDS CLARIFICATION] markers remain
  - 用户对话已经明确所有关键决策（明确报错 vs fallback 用户位置、走完整 spec 流程）
- [x] Requirements are testable and unambiguous
  - 每条 FR 都有 MUST/MUST NOT、可程序判断
- [x] Success criteria are measurable
  - SC-001 (≥95%) / SC-002 (=100%) / SC-003 (0%) / SC-004 (P95<500ms) / SC-005 (=1 次) / SC-006 (3 个 query 全过)
- [x] Success criteria are technology-agnostic (no implementation details)
  - 备注：SC-004 提「amap 调用引入的延迟」、SC-005 提「amap API 调用次数」—— 用了「amap」这个具体外部依赖名。但这是**用户需求里指定的集成对象**、无法用更抽象的词替代（PM 关心的就是这个具体 API 的成本和延迟）。
- [x] All acceptance scenarios are defined
  - 3 个 US 共 9 个 Given/When/Then 场景
- [x] Edge cases are identified
  - 8 条 Edge Cases（超时/配额/低置信度/英文/数字 query 等）
- [x] Scope is clearly bounded
  - Out of Scope 7 条明确说明不做什么
- [x] Dependencies and assumptions identified
  - Assumptions 7 条（amap key/配额/网络/Redis/中文/AI 联网/内容稀缺独立问题）

## Feature Readiness

- [x] All functional requirements have clear acceptance criteria
  - FR-001~014 都和 US/SC 关联
- [x] User scenarios cover primary flows
  - US1 amap 命中（核心修复）/ US2 amap 也识别不到（明确报错）/ US3 字典快路径（性能护栏）
- [x] Feature meets measurable outcomes defined in Success Criteria
  - SC 全部可程序化验证
- [x] No implementation details leak into specification
  - 同 "Content Quality" 第一条备注：amap/Redis/geocode_query 是用户指定的集成边界，不是实现细节

## Notes

- 本 spec 是 spec-001 → hotfix 路径（spec-017 之前用手工字典 PROVINCE_CENTERS 兜底）的根本解
- 实现期复用 places.py 的 `geocode_query`（spec-005 实现），减少重复工作和风险
- US2 的「明确报错」是用户在 AskUserQuestion 里明确选过的（vs 「fallback 到用户当前位置」）
- Items 全部通过、可进入 `/speckit-clarify` 或 `/speckit-plan` 阶段
