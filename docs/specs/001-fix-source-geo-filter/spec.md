# Feature Specification: 来源点位与搜索词地理一致性修复

**Feature Branch**: `001-fix-source-geo-filter`

**Created**: 2026-05-18

**Status**: Clarified（已澄清 3 个关键决策，可进入 plan 阶段）

**Input**: 用户描述："搜「上海露营地」时，底部「来源点位 47」里前 36 个卡片是杭州/余杭/烟台牟平/烟台福山等地的点位（早期 DB 冷启动数据），与"上海"完全无关。用户看起来像"搜索功能没生效"。

根因：前端按地图视野 80km 半径拉 DB 数据，没按搜索词识别出的 detected_place 过滤；DB 里有早期录入的全国散点。

期望：当 detected_place 存在时，places API 只返回该地理范围内的点位；如果没有就返回空 + 友好空状态（不要拿外地点位凑数）。"

---

## Clarifications

### 2026-05-18 Round 1（用户已答）

- **Q1：前后端怎么传"地理意图"？** → **B**：places API 自己 detect。前端只需把 query 字符串传给 places API（**新增 `q` 参数**），后端在 API 内部调 `detect_place_center` 决定 search_center。前端最简，后端集中决策。
- **Q2：detect 不识别的地名（如"漠河"）怎么办？** → **高德 geocoding API 兜底**。先用本地 `detect_place_center`（14 个城市表，快），失败 fallback 到高德 geocoding API（慢但全），高德也失败再走"用户位置"。
- **Q3：空状态 UI 怎么显示？** → **底部卡片区显示一句话**，不动 AI 答案区。卡片区文案："该地区暂无点位，AI 仍在为你联网搜索"。

---

## User Scenarios & Testing *(mandatory)*

### User Story 1 - 搜索结果与地名严格一致（Priority: P1）

用户在搜索框输入"上海露营地"，期望看到的「来源点位」列表里只有上海地理范围内的露营/驻车点位，不会混入杭州、烟台等其他地方的点位。

**Why this priority**: 搜索功能的**核心信任契约**。搜「上海」给「烟台」的结果，用户会立刻怀疑产品的可靠性。这一条独立修复就能解决 80% 的尴尬演示场景。

**Independent Test**: 浏览器搜「上海露营地」，断言底部「来源点位」前 10 张卡片**所有的经纬度**都在上海行政区域内（lat 30.7-31.9, lon 120.9-122.1）。

**Acceptance Scenarios**:

1. **Given** 用户在杭州地区使用产品，**When** 搜索"上海露营地"，**Then** 返回的所有点位经纬度都在上海行政区域内
2. **Given** DB 里既有杭州 36 个 + 上海 11 个点位，**When** 搜索"上海露营地"，**Then** 只返回 11 个上海点位
3. **Given** 搜索"莫干山自驾露营"，**When** 接口返回数据，**Then** 所有点位都在莫干山周边（lat 30.5-30.8, lon 119.8-120.1）

---

### User Story 2 - 友好空状态（Priority: P2）

当用户搜索的地区 DB 里没有数据时（例如"漠河露营"），应明确告诉用户"该地区暂无数据"，**不回退到展示其他地方的数据凑数**。

**Why this priority**: 没有它，P1 修完后会出现"搜上海但 DB 还没录入上海"的过渡态，用户看到空白屏会疑惑。优先级低于 P1 因为没 P1 这条就无效。

**Independent Test**: 浏览器搜一个 DB 里没数据的地名（如"漠河"），断言「来源点位」区显示"该地区暂无点位，AI 仍在为你联网搜索"文案，列表卡片数 = 0。

**Acceptance Scenarios**:

1. **Given** DB 里没有任何漠河附近的点位（且高德 geocoding 能识别"漠河"），**When** 搜索"漠河露营"，**Then** 前端在卡片区显示"该地区暂无点位，AI 仍在为你联网搜索"，卡片数 = 0
2. **Given** 后端 places API 返回 `[]`，**When** 前端接收响应，**Then** 不显示卡片列表，只显示居中的友好提示文案

---

### User Story 3 - 无地理意图时保留原行为（Priority: P3）

当用户搜索词不包含任何地名（既不在 14 城市表，高德 geocoding 也识别不出地理位置），应保留原行为（按用户当前位置 80km 半径返回结果）。

**Why this priority**: 回归防护 —— 不能因为修复 Bug 2 反而破坏老的"附近"搜索体验。

**Independent Test**: 搜索"露营"（无地名），返回的点位都在当前用户位置 80km 半径内（与修改前一致）。

**Acceptance Scenarios**:

1. **Given** 用户当前位置在杭州（30.27, 120.15），**When** 搜索"露营"（detect 和高德 geocoding 都返回 null），**Then** 返回杭州周边 80km 的点位（行为不变）
2. **Given** `detect_place_center` 和高德 geocoding 都失败，**When** 后端处理 places 请求，**Then** 使用前端传入的用户当前坐标作为搜索中心

---

### Edge Cases

- **搜索词含多个地名**（如"上海北京"）：用 detect_place_center 返回的第一个匹配地名（现有实现，本次不改）
- **搜索词是 detect 未识别但高德能识别的地名**（如"漠河"、"乌鲁木齐"、"喀什"）：走高德 geocoding fallback，**算"有地理意图"**，触发严格过滤 + 友好空状态
- **detected_place 是省份**（如"浙江"）：使用该省份中心 + 80km（本次保持，不扩大半径）
- **用户手动拖动地图后再搜索**：搜索词的地理意图**优先**于地图当前视野（明确决策）
- **AI 联网搜索仍能拉到非本地点位**：本 spec 只管 DB 数据过滤，**不影响** AI 联网搜索结果
- **后端 cache 命中**：cache key **MUST** 包含 search_center 信息
- **高德 geocoding API 失败/超时**：fallback 到 detected_place=null 分支（用户位置 80km，不阻塞 user）
- **高德 geocoding API quota 用尽**：同上 fallback；但要监控（FR-009 缓存机制减少这种情况）

---

## Requirements *(mandatory)*

### Functional Requirements

#### 后端 places API 改造

- **FR-001**: `/api/v1/places` 接口 **MUST** 新增可选参数 `q`（query 字符串），由前端搜索时传入
- **FR-002**: 当 `q` 参数存在时，后端 **MUST** 按以下顺序确定 search_center：
  1. 先调 `detect_place_center(q)` —— 命中本地 14 城市表则用该坐标
  2. 未命中则调**高德 geocoding API** 解析 `q` 为坐标（带超时 2s）
  3. 仍失败则 fallback 到前端传入的 `lat`/`lon`（保持原行为）
- **FR-003**: search_center 确定后，**MUST** 用 PostGIS `ST_DWithin` 在 80km 半径过滤；过滤后无结果 **MUST** 返回空数组 `[]`，**禁止** fallback 到无地理约束的全表数据
- **FR-004**: 当 `q` 参数不存在 / 为空时，**MUST** 保留原行为：用前端传的 `lat`/`lon` 作为中心
- **FR-005**: places API 响应 **MUST** 在 metadata 区返回 `{detected_place: string | null, search_center: {lat, lon} | null, geocoder: "local" | "amap" | null}` 三个字段，让前端知道命中了哪种识别方式

#### 高德 geocoding 集成

- **FR-006**: 后端 **MUST** 新增 `geocode_query(q: str) -> tuple[lat, lon, name] | None` 服务函数，调高德 `/v3/geocode/geo` API，使用现有 `AMAP_WEB_KEY`
- **FR-007**: `geocode_query` 调用 **MUST** 用 Redis 缓存结果，key=`geocode:{md5(q)}`，TTL 7 天（同一地名查询不重复调高德）
- **FR-008**: `geocode_query` 调用 **MUST** 带 2s 超时；失败/超时 **MUST** 静默返回 None，不向上抛错

#### 前端 places 调用 + 空状态

- **FR-009**: 前端在搜索时调 `/api/v1/places` **MUST** 把当前 query 通过 `q=<query>` 参数传给后端
- **FR-010**: 前端在收到空 places 结果且响应中 `search_center !== null`（即识别出了地理意图）时，**MUST** 在「来源点位」卡片区显示文案："该地区暂无点位，AI 仍在为你联网搜索"
- **FR-011**: 前端在收到空结果且 `search_center === null`（无地理意图）时，**MUST** 显示原有空状态（沿用现有 UI）

#### Cache 键变更

- **FR-012**: 后端 `list_places` cache key 计算 **MUST** 包含 `search_center` 的 lat/lon（精度到小数点后 2 位）+ `radius_km`，避免不同地名搜索误命中同一 cache

### Key Entities

- **Place**: 露营/驻车点位（已有），核心字段 `latitude` / `longitude` / `name` / `ai_summary` / `category`
- **DetectedPlace**: 从 query 中识别出的地理意图，`{lat: number, lon: number, name: string, source: "local" | "amap"}` 或 `null`
- **SearchCenter**: 实际用于 PostGIS 过滤的中心点，按 FR-002 顺序解析

---

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: 搜「上海露营地」后，返回的所有 Place **100%** 在上海行政区内（lat 30.7-31.9, lon 120.9-122.1）—— 当前 ~25%
- **SC-002**: 搜「莫干山」后，返回的所有 Place **100%** 在莫干山周边 80km 内
- **SC-003**: 搜 DB 无数据的城市（如"漠河"）：高德识别成功 → 返回空 + 前端显示空状态文案；高德也失败 → 行为同搜"露营"
- **SC-004**: 搜「露营」（无地名），行为与修改前一致（用户当前位置 80km），**0 个回归**
- **SC-005**: pytest 新增 **4 条 regression test**（3 个 User Story + 1 个 geocoding fallback），全部通过
- **SC-006**: 演示时再搜「上海/莫干山/北京」3 次，老师**看不到**与搜索词无关的卡片
- **SC-007**: 高德 geocoding API 调用，同一 query 7 天内最多打**1 次**（cache 生效）

---

## Assumptions

- `detect_place_center` 已实现，支持 14 个国内主要城市 + 浙江各市县（commit `b4f76cc`）
- **高德 `AMAP_WEB_KEY` 已配置在 `.env` 里**（具体值见本地 .env，不在版本控制内）
- 高德 geocoding API 免费额度足够开发期使用（每天 100 次起步，cache 7 天后实际调用频率会很低）
- PostGIS `ST_DWithin` 索引已就绪（commit `7806c9c`）
- Redis 缓存层已就绪（commit `29c772a` 引入）
- "AI 联网搜索"的结果区**不在本 spec 范围**（那条流程是 SSE 流式，已正常按 query 拉外网）
- 用户演示场景：搜索词带明确地名（"上海/莫干山/淳安"等）
- 不在本次范围：DB 冷启动数据清洗（"烟台/牟平/福山"等历史脏数据保留在 DB，只是搜索时被地理过滤掉，看不见即可）
