# Feature Specification: 治本 —— AI 抽精确地址 + geocoding 加 city hint

**Feature Branch**: `main`

**Created**: 2026-05-19

**Status**: Clarified（用户已明确两件事都做）

**Input**: 昨天 spec 003/004 修了"模糊点位不出 marker + 历史脏数据不展示"（治标）。今天治本：让 AI 从源头抽**更精确**的地址 + geocoding 加 city hint 减少歧义（如"莫干山"被高德识别成甘肃）。

## Clarifications

用户决策直接给定：

- **Q1：AI prompt 改成什么粒度？** → 强迫 AI **要么抽到街道/门牌精确度**，要么把模糊点位**直接放 unmapped**（不放 spots）。从源头减少进入 geocode 流程的"上海"级模糊地址。
- **Q2：geocode_query 加 city/province 参数怎么传？** → 调用时传 `raw.get("city")` 和 `raw.get("province")`（AI 已经在 spots 里输出了这些字段）。高德识别时优先在该城市内匹配。
- **Q3：「莫干山」歧义具体怎么处理？** → 不用为单个地名特化，让 city hint 机制覆盖所有类似情况。

## User Scenarios & Testing

### User Story 1 - AI 抽到精确地址（Priority: P1）

AI 联网搜索拿到的网页里如果地址精确（"上海市闵行区浦江镇 XX 路 1 号"），spot 进 spots 列表；如果地址只到城市级（"上海"、"市中心"），**直接进 unmapped**（不让它进入 geocode 流程产生市中心 fallback）。

**Why this priority**: 配合 spec 003，从**源头**减少模糊点位。spec 003 是"防火墙"（geocode 失败拦），这条是"上游堵漏"。

**Independent Test**: 构造一个 AI 返回结果含"地点名：上海某营地，地址：上海" → 经过 normalize 后该 spot **在 unmapped**，**不在 spots**。

**Acceptance Scenarios**:

1. **Given** AI 抽出 `{name: "XX 营地", address_hint: "上海市闵行区浦江镇XX路1号"}`, **When** normalize_candidates 处理, **Then** 进 spots（精确地址，正常 geocode）
2. **Given** AI 抽出 `{name: "上海某营地", address_hint: "上海"}` 或 `{address_hint: ""}`, **When** normalize, **Then** 进 unmapped 不进 spots
3. **Given** AI 抽出 `{name: "XX 公园", address_hint: "市中心"}`, **When** normalize, **Then** 进 unmapped

---

### User Story 2 - geocode_query 加 city hint（Priority: P1）

调高德 geocoding 时附带 city / province 信息，缩小歧义搜索空间，让"莫干山"在浙江省内匹配（而非甘肃同名地）。

**Why this priority**: spec 002 引入 geocode_query 时只传 q 字符串，导致高德返回**全国第一个匹配**。加 hint 是直接缓解。

**Independent Test**: 调 `geocode_query("莫干山", city="湖州市")` 应该返回浙江莫干山坐标（30.6, 119.9），不再是甘肃。

**Acceptance Scenarios**:

1. **Given** `geocode_query("莫干山", province="浙江省")`, **When** 调高德 API, **Then** 返回浙江莫干山（lat ~30.6）
2. **Given** `geocode_query("莫干山")`（无 hint，保持旧行为）, **When** 调用, **Then** 仍可能返回甘肃同名地（向后兼容）
3. **Given** 调用方 places.py 现有逻辑, **When** 走 geocode_query 兜底, **Then** 自动把 raw query 里的省份关键词传进去

---

### User Story 3 - 不破坏现有 high/medium 精度场景（Priority: P2 回归防护）

精确地址（已经能 geocode 到 high/medium）的处理路径**不受影响**。

**Independent Test**: 跑现有 9 + 8 + 8 + 3 + 3 = 31 条 spec 001-004 相关测试，全部 pass。

## Requirements

### Functional Requirements

#### AI prompt 修订（治本）

- **FR-001**: `normalize_candidates` 函数 **MUST** 在处理 spot 时判断 `address_hint` 精度：
  - 如果 address_hint 只包含**城市级关键词**（"上海"、"杭州"、"市区"、"市中心"），**MUST** 进 unmapped 不进 spots
  - 判断方法：精确地址应至少含**街道/路/号/村/镇**等关键词之一
- **FR-002**: AI extraction prompt（line 888 附近）**MUST** 加新规则：
  > "address_hint 必须包含街道/路/号/村/镇/景区具体位置；只到城市级（如'上海'、'杭州'）就放 unmapped_candidates 而不是 spots"

#### geocode_query 加 city hint

- **FR-003**: `geocode_query` 函数签名 **MUST** 扩展为接受可选 `city: str | None = None` 和 `province: str | None = None` 参数
- **FR-004**: 当传入 hint 时，**MUST** 在高德 API 调用的 params 里加 `city=<city>`（高德支持）
- **FR-005**: 调用方（`backend/app/routers/places.py:_resolve_search_center`）**MUST** 从 query 里提取省份关键词作为 hint 传入（复用现有 `_PROVINCE_KEYWORDS` 或 `_infer_province_from_text`）

### Key Entities

- **AddressPrecision**: 地址精度判断（street_level / city_level / unknown）
- **GeocodeQueryHint**: `{city: str | None, province: str | None}` —— 减少歧义

## Success Criteria

- **SC-001**: 跑 `geocode_query("莫干山", province="浙江省")` 返回**浙江**莫干山（lat 30.5-30.8），**不**返回甘肃
- **SC-002**: AI 返回 spot 含 `address_hint="上海"`（只城市级）**MUST** 进 unmapped 而非 spots
- **SC-003**: 浏览器实测搜「莫干山自驾」**marker 落在浙江德清/湖州**（之前可能在甘肃）
- **SC-004**: 已有 42 测试 **0 回归** + 新增 ≥4 条 regression test
- **SC-005**: 浏览器实测搜「上海露营地」展示的**精确 marker 数量** 不少于昨天（即治本不会过度筛减）

## Assumptions

- AI 模型（Ark Seed）会**遵守新 prompt rule**（不会偷偷给"上海"级别的 spot）—— 如果不遵守，FR-001 的后端兜底过滤保证
- 高德 REST API `city` 参数支持城市名（spec 已验证）
- 「上海」「杭州」这种 2-3 字城市名作为黑名单**够用**（不需要 NLP 解析）
- 不动现有 detect_place_center 字典（spec 001 已覆盖）
