# Feature Specification: 搜索地理意图识别 amap geocoding 兜底

**Feature Branch**: `017-amap-geo-fallback`

**Created**: 2026-05-23

**Status**: Draft

**Input**: 用户真机搜「大庆露营地」识别不到 → 临时补字典 39 个城市；接着搜「景德镇露营地」仍然不行（字典还是没收录）。靠手工字典永远盖不完中国 300+ 地级市。需要根本解：自动调用 amap geocoding API 兜底，让任何中国地名都能被识别；amap 也识别不到时明确报错，不悄悄 fallback 到默认坐标误导用户。

## Clarifications

### Session 2026-05-23（AI-resolved defaults，无用户级 PM 歧义）

无关键 PM/UX 决策需要用户拍板（用户明确授权技术决策自主拍板）。以下 5 条技术细节由实施方自主决定并固化进本 spec：

- Q: 缓存策略对「识别失败」查询如何处理？→ A: **失败结果（unrecognized_location）也缓存 24h**，避免重复调 amap 浪费配额；用户改 query 自然命中新 cache key、无需手动失效。
- Q: query 归一化规则（缓存键）？→ A: **`trim + 连续空白合一` 后作为缓存 key**；不 lowercase（中文无大小写区分）、保留中文原文。
- Q: amap 返回 formatted_name 如何展示？→ A: **直接透传完整字符串**（如「江西省景德镇市」）作为 detected_place 字段；前端展示原样不裁剪。
- Q: 多地名 query（如「上海到北京自驾」）处理？→ A: **沿用现有 detect_place_center 行为**——按 token 顺序第一个匹配优先（与字典快路径一致）；不在 spec-017 内引入「路线」语义。
- Q: amap 调用日志格式？→ A: **每次调用记录 `{query, result_source, latency_ms, cache_hit, status}`** 到后端 logger，便于 grep 监控配额和成功率。

## User Scenarios & Testing *(mandatory)*

### User Story 1 - 任何地名都能正确定位（Priority: P1）

用户搜「景德镇露营地」「莫干山民宿」「九华山徒步」「拉萨大昭寺附近」这种**不在字典里但真实存在**的地名 + 主题词组合时，系统应当自动识别地名位置、把地图视野跳到对应城市/景点、AI 联网搜出**该地区**的相关内容。

**Why this priority**：这是当前**最大体验崩坏**——用户搜任何非省会的地级市都得不到正确结果。中国 300+ 地级市 + 几千区县 + 无数景区，靠手工字典永远盖不完。这条修了，用户才能真正在「任何地区」搜出露营地（用户原话："连塔克拉玛干沙漠地区都能搜到呢，为什么其他地区搜不到？"）。

**Independent Test**：真机搜「景德镇露营地」，预期：
1. 地图视野自动跳到江西景德镇市
2. 底部 sheet 显示「detected_place=景德镇」
3. AI 整理结果包含景德镇本地的露营内容（来源是江西本地媒体/景德镇本地公众号/小红书等）
4. marker 落到景德镇周围（不是杭州/苏州）

**Acceptance Scenarios**：

1. **Given** 用户输入「景德镇露营地」+ 当前位置在杭州，**When** 点击 AI 搜索，**Then** 地图视野跳到景德镇市中心、AI 返回景德镇本地露营地点位、marker 出现在景德镇周围 80km 内
2. **Given** 用户输入「莫干山民宿驻车」（莫干山在字典里、但「驻车民宿」不是常见组合），**When** 搜索，**Then** 系统优先用字典命中莫干山坐标（快路径）、不调 amap
3. **Given** 用户输入「张家界自驾营地」（张家界已在字典）+ 当前位置任意，**When** 搜索，**Then** 走字典快路径、不调 amap、响应时间和 hotfix 前一致

---

### User Story 2 - 识别不到地名时明确报错（Priority: P1）

用户输入**完全不存在的地名**（如「火星二号营地」「赛博朋克镇」「乱按键盘 asdfgh」）时，系统应当**明确告知「无法识别地名」**、不要悄悄 fallback 到默认杭州坐标然后返回一堆杭州周围的杂数据让用户误以为「搜到了」。

**Why this priority**：和 US1 同等重要——「错误的成功」比「明确的失败」更糟糕。用户当前搜「景德镇」看到杭州结果会以为「景德镇就这些点位」、对产品失去信任。明确报错让用户知道「这个地名我们识别不出来、请换个说法」、保留信任。

**Independent Test**：真机搜「火星二号营地」，预期：
1. 地图视野**保持当前位置**（不跳到杭州）
2. 显示明确提示文案「无法识别您输入的地名「火星二号营地」，请尝试更明确的地名（如「南昌露营地」「莫干山民宿」）」
3. 底部 sheet 不展示底库其他地区的杂数据
4. 用户能继续修改 query 重搜

**Acceptance Scenarios**：

1. **Given** 用户输入「火星二号营地」+ 当前位置在杭州，**When** 搜索，**Then** 显示「无法识别地名」错误文案、地图视野**不**跳到杭州默认中心、不显示底库杂数据
2. **Given** 用户输入纯主题词「免费露营地」（无地名），**When** 搜索，**Then** 保持现有行为（用用户当前位置作中心，不触发 unrecognized_location 错误——这种 query 本来就是「找附近的」、不是 bug）
3. **Given** amap API 超时 / 网络失败 / 返回 0 候选，**When** 搜索，**Then** 同样返回 unrecognized_location（用户体验等同于 amap 也识别不到）

---

### User Story 3 - 字典快路径性能不退化（Priority: P2）

字典已经命中的 query（如「南昌露营地」「大庆露营地」「莫干山附近」）必须**直接用字典坐标**，不要为了「保险起见」每次都调 amap——这会让常用 query 响应时间从 ~10ms 变成 ~300ms，体验明显变差。

**Why this priority**：性能护栏，避免根因修法引入性能回归。字典是 spec-001 → hotfix 一路积累的「快路径」，对常用 query（90%+ 流量）非常关键。

**Independent Test**：连续搜「南昌露营地」10 次，预期：
1. 每次 detect_place_center 走字典命中（不调 amap）
2. 后端日志无 amap.geocode 调用记录
3. 响应时间 < 50ms（DB 查询本身的时间，不算 AI 联网部分）

**Acceptance Scenarios**：

1. **Given** 用户搜「南昌露营地」（字典已命中），**When** 后端 detect_place_center 执行，**Then** 字典 substring 匹配第一时间返回、不调 geocode_query、后端日志无 amap 调用
2. **Given** 用户搜「黄山露营」（字典已命中黄山），**When** 后端处理，**Then** 字典命中、不调 amap
3. **Given** 用户连续搜 10 次「景德镇露营地」（字典未命中、amap 命中），**When** 后端处理第 2~10 次，**Then** 第 1 次调 amap 写缓存、第 2~10 次走 Redis 缓存命中、amap API 调用次数 = 1

---

### Edge Cases

- **amap 返回多个候选地名**（如「北京」可能返回北京市/北京路）：取**第一个**（amap 默认按相关度排序），不展开多选 UI
- **amap 返回低置信度结果**（如「火星」可能返回某个偏僻小村的「火星村」）：当前**信任 amap 的判断**（amap 自己会过滤掉太离谱的）；后续如果发现误判多再加置信度过滤
- **amap API 调用超时**（>3s）：等同识别失败 → unrecognized_location
- **amap API 配额耗尽 / 限流 503**：等同识别失败 → unrecognized_location + 后端日志告警
- **query 全是数字 / 特殊符号**（如「12345」）：amap 大概率识别不到 → unrecognized_location
- **query 是英文地名**（如「Beijing camping」）：amap 中文 API 可能识别不到 → unrecognized_location（不在本 spec 范围内深入解决）
- **query 包含已知地名 + 不存在地名**（如「火星北京」）：字典已经能命中「北京」、走快路径，本 spec 不变行为
- **缓存写入失败**（Redis down）：继续往下走（amap 调用本身成功就用 amap 结果）、不阻塞用户搜索

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: 系统在字典（PROVINCE_CENTERS + ZHEJIANG_COORDS）未命中 query 中任何地名时，**MUST** 自动调用 amap geocoding API 进行兜底识别
- **FR-002**: 系统 **MUST** 复用 `places.py` 已有的 `geocode_query` 函数（spec-005 实现、测试已覆盖），不重复实现 geocoding 逻辑
- **FR-003**: 系统 **MUST** 把 amap 返回的 `(lat, lon, formatted_name)` 用作 search API 的 `effective search_center`，并体现在响应的 `source_breakdown.search_center` 和 `source_breakdown.detected_place` 字段
- **FR-004**: 系统 **MUST** 对 amap geocoding 调用设置 3 秒超时；超时等同识别失败
- **FR-005**: 系统 **MUST** 缓存 amap geocoding 结果到 Redis、TTL = 24 小时（**含识别失败结果**，避免重复调 amap 浪费配额）；同 query 24h 内重复搜不重复调 amap。缓存键采用归一化后的 query（trim + 连续空白合一，保留中文原文、不 lowercase）。
- **FR-006**: 系统 **MUST** 在 amap 也识别不到（返回空/超时/异常）时返回 `warning_code = 'unrecognized_location'` + 中文 warning 文案
- **FR-007**: 系统 **MUST NOT** 在 amap 识别失败时悄悄 fallback 到任何默认坐标（包括杭州 30.27/120.15、用户当前位置）作为 effective search_center
- **FR-008**: 前端（小程序端）**MUST** 在收到 `warning_code = 'unrecognized_location'` 时显示明确错误文案（含用户输入的原 query 作引用）
- **FR-009**: 前端 **MUST** 在收到 `warning_code = 'unrecognized_location'` 时**保持地图当前视野不变**（不调 `setSearchCenter`）
- **FR-010**: 前端 **MUST** 在收到 `warning_code = 'unrecognized_location'` 时不展示底库其他地区的杂数据（不调底库 `/places` 接口、或者展示空状态）
- **FR-011**: 字典命中的 query **MUST** 直接使用字典坐标、**MUST NOT** 触发 amap 调用（性能保护）
- **FR-012**: 系统 **MUST** 保持 `places.py` 已有的 amap fallback 逻辑不变（避免回归现有 `/api/v1/places?q=xxx` 行为）
- **FR-013**: query 不含任何地名时（如「免费露营地」），**MUST** 保持现有「用用户当前位置作中心」的行为；**MUST NOT** 触发 amap 调用、**MUST NOT** 返回 unrecognized_location
- **FR-014**: 系统 **MUST** 在后端日志记录 amap 调用情况，字段固定为 `{query, result_source, latency_ms, cache_hit, status}`（`result_source ∈ {'dict','amap','none'}`、`status ∈ {'ok','timeout','error'}`），便于后续 grep 监控配额和成功率

### Key Entities *(include if feature involves data)*

- **Geocode Result**：地理编码结果，包含
  - `query`（用户搜索关键词，归一化后）
  - `latitude` / `longitude`（地理坐标）
  - `formatted_name`（amap 返回的标准化地名，如「江西省景德镇市」）
  - `source`：'dict'（字典命中）/ 'amap'（amap geocoding 命中）/ 'none'（识别失败）
- **Warning Code**：系统警告类型，新增枚举值 `'unrecognized_location'`（加入现有 warning_code 列表，如 'extract_timeout' / 'network_error' 等）
- **Geocode Cache Entry**：Redis 缓存条目
  - key：`amap:geocode:{query_normalized}`，其中 `query_normalized` = `query.strip()` 后 `re.sub(r'\s+', ' ', x)`（合并连续空白）、保留中文原文不 lowercase
  - value：序列化的 Geocode Result（含 source ∈ {'dict','amap','none'}、坐标、地名）；识别失败也缓存（source='none'）
  - TTL：24 小时（命中和失败统一 TTL）

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**：用户搜中国任意地级市 / 区县 / 知名景点名称组合（共抽样 30 个 query，覆盖东西南北中各 6 个），地理识别成功率 ≥ **95%**（spec-017 之前字典覆盖率 ~20%）
- **SC-002**：搜不存在地名（10 个 fuzz query 样本）时，返回明确 `unrecognized_location` 错误的比例 = **100%**（不再悄悄 fallback 杭州、不再展示底库杂数据）
- **SC-003**：字典命中的 query（10 个 sample，如「南昌露营地」「莫干山」「大庆露营地」），**0% 触发 amap 调用**（字典快路径保护）
- **SC-004**：amap 调用引入的端到端延迟 **P95 < 500ms**（含 3s 超时上限）；缓存命中时 < 30ms
- **SC-005**：同 query 24 小时内重复搜，amap API **调用次数 = 1**（即首次后全部缓存命中）
- **SC-006**：真机端到端验证：搜「景德镇露营地」/「莫干山民宿」/「拉萨大昭寺附近」三条 query，**全部**能识别地名 + 地图视野跳对 + AI 联网返回该地区相关内容（用户级感知验收）

## Assumptions

- amap API key（`AMAP_WEB_KEY`）已配置在 backend `.env`，且 quota 充足（高德个人开发者免费配额 5000 次/天，远高于当前预期使用量）
- amap geocoding API 在中国大陆境内稳定可达（无需海外代理）
- `places.py` 的 `geocode_query` 函数行为稳定（spec-005 实现 + `test_q_unknown_city_amap_fallback` 测试覆盖）
- Redis 服务可用（当前 docker `camping_ai-redis-1` 长期在跑）
- 用户搜索的地名以**中文中国大陆**地名为主（港澳台/海外不在范围内）
- AI 联网搜索引擎（Ark Seed 2.0）本身工作正常（与 detect_place_center 独立）
- 「冷门地区互联网内容少」是独立问题（如大庆露营内容稀缺）—— spec-017 只解决**地理意图识别**，不解决**内容稀缺**

## Out of Scope

- 不改 `places.py` 已有 amap fallback 逻辑（spec-005 已稳定、跑过测试）
- 不改 `PROVINCE_CENTERS` 字典内容（hotfix 已 commit `2b720f9`，本 spec 保留字典作为快路径）
- 不引入 LLM 判断地理意图（amap 数据已够覆盖、引入 LLM 会增加成本和延迟）
- 不动 H5 端的 stream 路径（H5 当前仍走 `/api/v1/search/stream`，未来另议；本 spec 只优化非流式降级路径 = 小程序场景）
- 不解决「冷门地区互联网内容少」问题（如搜大庆只能找到 1 年前的内容、这是 AI 联网搜索引擎能搜到的内容范围问题、不是地理识别问题）
- 不引入新的 geocoding 提供商（如百度地图、Mapbox），只用 amap 一家（已经在产品里用了）
- 不做多语言 geocoding（不支持英文地名识别）
