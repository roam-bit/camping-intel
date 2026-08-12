# Feature Specification: places API 过滤低精度历史脏数据

**Feature Branch**: `main`

**Created**: 2026-05-18

**Status**: Clarified

**Input**: 用户截图：杭州地图上展示了「烟台市福山区...河畔营地」这条点位。原因是 spec 003 之前老代码 geocode 失败时生成了"猜测坐标"（杭州周边）并存进 DB，标记 `location_confidence: "low"`。spec 003 修了"以后不再猜"但**没清旧数据**（2011 条 low 占总数 91%）。

用户决策：「**开 spec 004 修，A 方案：API 过滤 low confidence**」。

## Clarifications

- **Q1：直接过滤 low 会让数据量从 2198 → 187（杭州 80km 从 470 → 65），可接受吗？** → 接受。65 个 medium 足够演示，且**没有错位 marker** 才是核心契约。

## User Scenarios & Testing

### User Story 1 - 不出现"地址与坐标不一致"的脏数据（Priority: P1）

用户在杭州打开页面，**不再**看到「福山区（烟台）」、「牟平区（烟台）」这种与当前位置无关的点位。

**Independent Test**: 调 `/api/v1/places?lat=30.27&lon=120.15` 断言**返回的所有 Place** 的 `location_confidence` 都不是 `"low"` 或 `"pending"`。

**Acceptance Scenarios**:

1. **Given** DB 有 405 条 low + 65 条 medium Place 在杭州 80km 内，**When** 不带 q 拉 places，**Then** 返回 ≤65 条（low 全过滤）
2. **Given** Place 表里有"烟台福山区..."坐标在杭州周边、confidence=low 的脏数据，**When** 拉 places，**Then** 该 Place **不**出现在结果

---

### User Story 2 - 不影响正常 medium/high 数据（Priority: P2 回归防护）

confidence=high 或 medium 的 Place **不**受影响。

**Independent Test**: 创建一条 confidence=medium 的 Place，断言 list_places 返回它。

## Requirements

- **FR-001**: `/api/v1/places` 接口 **MUST** 在 SQL 层面过滤 `Place.location_confidence IN ('high', 'medium')`（不再展示 `low` / `pending` / NULL）
- **FR-002**: 过滤逻辑放在 base_filters 里（与现有 `status='active'` 同层），**MUST** 与 q / detect_place_center / 高德 fallback 等 spec 001 逻辑兼容
- **FR-003**: 不动 Place 表数据（无 DELETE / UPDATE）；只动查询逻辑
- **FR-004**: pytest 加 1 条 regression test（low/pending Place 不返回）

## Success Criteria

- **SC-001**: 浏览器刷新（不搜任何词）→ 杭州地图上**不再**显示"福山区/牟平区/烟台"等错位 marker
- **SC-002**: 41 个现有 pytest **0 回归** + 1 条新 regression test pass = 42 passed
- **SC-003**: 演示时搜「上海/莫干山/北京」**不再**出现地理错位点位

## Assumptions

- 现有 DB 里 confidence=high 的 Place = 0（先看 SQL 验证），medium=187 足够展示
- 用户接受"演示 marker 数量减少"作为换取"质量提升"的 trade-off
- 不动旧脏数据 → 仍占 DB 91% 空间，但用户不可见；未来可单独开 spec 做数据清洗
