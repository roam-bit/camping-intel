# Feature Specification: 模糊位置点位不出 marker（Bug 1 修复）

**Feature Branch**: `main`（spec 003 直接进 main）

**Created**: 2026-05-18

**Status**: Clarified（用户决策已直接给定，无需额外 clarify）

**Input**: 用户截图发现搜「上海露营地」结果里有 marker 落在**黄浦江/外滩**（陆地外的水面上）。

用户的产品决策（原话）：「如果是后端定位精度不够导致的就通过优化代码解决，如果是信源里给的地理位置就很模糊无法精确定位的话就直接筛掉这个信源和点位。」

诊断结果：当前是**后者**——`ai_service.py:1110-1121` 在 `geocode_with_amap` 失败时 fallback 到 `fallback_center` 生成"近似坐标"作为占位 marker。这些坐标落到省份/城市中心，恰好在水面上（上海市中心 ≈ 黄浦江）。代码用 `location_confidence: "low"` 标记了，但前后端都没用这个信号过滤。

## Clarifications

用户决策已经在原话里直白给出，**两路决策**：

- **Q1：geocode 完全失败（geo is None）**怎么办？ → **筛掉这个点位**，不创建 Place / 不出 marker。但保留 AI 提炼文字（用户仍能看到"漾域农场地址：吕巷镇红光路 1101 号"）→ 把该 spot 放进 `unmapped_candidates` 列表。
- **Q2：geocode 成功但 confidence=low**（不到 high/medium）？ → 同样筛掉，不出 marker。
- **Q3：要不要前端展示一个"该信源位置不准"的提示？** → 本次不加（保持最小改动，AI 文字里地址已经写明）。

## User Scenarios & Testing

### User Story 1 - 不出现"江里的 marker"（Priority: P1）

用户搜任何 query 时，地图上的所有 marker **必须**对应**精确地理位置**（geocode level ∈ {兴趣点, 门牌号, 道路}），**不会**出现在水面 / 远郊定位中心。

**Why this priority**: 这是地图产品的**信任契约**。一个 marker 落在江里，用户就会怀疑**所有** marker 的可信度。

**Independent Test**: 用 mock geocode 返回 `None` / 或 `confidence: "low"`，断言**对应的 spot 不出现在 places API 响应里**（应该出现在 unmapped_candidates）。

**Acceptance Scenarios**:

1. **Given** AI 抽取出 spot「漾域农场」, **When** `geocode_with_amap` 返回 None（地址识别失败）, **Then** 该 spot **不**生成 Place，**也不**进 spots 列表；而是进 `unmapped_candidates`（前端展示为"线索"文字，无 marker）
2. **Given** AI 抽取出 spot「上海某营地」, **When** `geocode_with_amap` 返回 confidence="low", **Then** 同上（drop 进 unmapped）
3. **Given** AI 抽取出 spot「上海闵行区浦江镇 XX 公园」精确地址, **When** `geocode_with_amap` 返回 confidence="medium" 或 "high", **Then** 正常进 spots，marker 落在精确坐标

---

### User Story 2 - unmapped 仍可见（Priority: P2 — 回归防护）

被筛掉的 spot **必须**仍然在 AI 提炼文字结果里展示（用户能看到文字描述），只是不进地图。

**Why this priority**: 不要因为防错 marker 把"信息消失"，那是回归。

**Independent Test**: search SSE 流 complete 时 `unmapped_candidates` 数组**包含**这个被筛的 spot。

**Acceptance Scenarios**:

1. **Given** 某 spot 因 geocode 失败被筛, **When** 用户看 SSE complete 响应, **Then** spot 出现在 `unmapped_candidates` 字段
2. **Given** AI 提炼文字"地点名：漾域农场，地址：吕巷镇红光路 1101 号", **When** marker 被筛, **Then** AI 提炼文字 **不变**（仍可读）

---

## Requirements

### Functional Requirements

- **FR-001**: `ai_service.py` 中 AI extract 后构造 Place 的流程，**MUST** 在 `geocode_with_amap` 返回 None 时**跳过该 spot**（不创建 Place），并把它加进 `unmapped_candidates`（不进 `spots` 列表）
- **FR-002**: 同 FR-001：当 geocode 返回 `confidence != "high"` AND `confidence != "medium"`（即 "low" 或 unknown）时，**MUST** 也跳过
- **FR-003**: 被筛掉的 spot **MUST** 在 unmapped_candidates 里包含 `reason` 字段说明原因（如 `"位置无法精确识别"`），供未来 debug
- **FR-004**: 现有 `spread_approximate_coord` + `fallback_center` 逻辑**保留**（用于其他场景），但 extract 主流程**不再调用**它们生成 marker
- **FR-005**: pytest 添加 regression test 覆盖三种情况：geocode None / confidence=low / confidence=medium（正常通过）

### Key Entities

- **Spot**: AI 从网页抽出的候选点位（dict，待 geocode）
- **Place**: 数据库表 + 地图 marker 实体（必须有精确坐标）
- **UnmappedCandidate**: 有信息但坐标无法精确识别的点位，只展示文字

## Success Criteria

- **SC-001**: 搜「上海露营地」后**所有** marker 都在陆地上（无水面 / 无市中心默认点）
- **SC-002**: 被筛的 spot 的"AI 提炼文字"仍展示（不丢信息）
- **SC-003**: pytest 加 3 条 regression test，全过
- **SC-004**: 现有 38 测试 **0 回归**
- **SC-005**: 浏览器实测搜上海/苏州/北京三种 query，**没有任何 marker 落在水面**

## Assumptions

- `geocode_with_amap` 已经过滤 level ∈ {国家, 省, 市, 区县}（amap_service.py line 89），返回 None 时**确实**意味着 "无法精确识别"
- 用户能接受"该信源没 marker 只有文字"作为模糊位置的展示方式（用户决策原话）
- 现有数据库里**已存的 Place（confidence=low）**本次不动（不回填清理）—— 下次 AI 重抽时新逻辑生效
- 改动只影响 AI 流式 extract 主路径（line 1099-1121 附近），不动其他 geocode 调用方
