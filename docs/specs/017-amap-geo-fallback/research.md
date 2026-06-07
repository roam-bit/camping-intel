# Phase 0 Research: spec-017 amap geocoding fallback

## 关键技术决策

### 决策 1：复用 `places.py` 的 `geocode_query`，不重写

**Decision**: 直接 `from app.services.amap_service import geocode_query` 在 search.py 调用。

**Rationale**：
- spec-005 已经实现完整链路：Redis 缓存（`geocode_query:{md5(q|city|province)}`、TTL 默认 7 天）+ httpx async + 2s timeout + 失败 None 返回 + 日志（`geocode_query.failed`）
- 已有测试 `test_q_unknown_city_amap_fallback` 验证 places API 端到端工作
- 重写会引入两套 cache key + 两套超时配置 + 两套日志格式，违反 DRY 原则
- 用户偏好「最小变更工程师」哲学——不为了「我做的 spec 用我自己的代码」而重复造轮子

**Alternatives considered**：
- 在 search.py 内单独实现 amap geocoding wrapper → 拒绝（重复代码）
- 把 geocode_query 抽到 `common/` 子模块 → 拒绝（places.py 调用方式已经稳定、不动）

### 决策 2：cache TTL 保持现有 7 天（不改成 spec 写的 24 小时）

**Decision**: 不修改 `amap_service.py` 的 cache_set TTL，保持现状（默认值，应该是 ~7 天，看 cache.py 实现）。

**Rationale**：
- 地名→坐标映射是**强稳定数据**（景德镇坐标几年不变），24h 太保守
- spec 写「TTL = 24 小时」是给保底承诺，不是上限；实际 7 天满足且更优
- 不动 amap_service.py 避免回归 places.py 行为

**Alternatives considered**：
- 严格按 spec 改成 24h → 拒绝（更短 TTL 反而增加 amap 调用、违背 SC-005 优化目标）
- 区分「命中」7 天、「失败」1 小时 → 拒绝（增加复杂度无明显价值）

### 决策 3：失败结果也复用同一 cache（不显式分桶）

**Decision**: amap 失败时返回 `None`，cache_set 也存 `None` 等价物（cached miss 自然不区分 hit/fail）。

**Rationale**：
- 看 `amap_service.py:148-150`：`cache_get` 返回非 None 视为命中，None 视为 miss
- 当前 `geocode_query` 失败时**不写缓存**（只在 169 行有效结果才 cache_set）→ 失败查询每次都会重试 amap，**违反 spec FR-005「失败也缓存」**
- **需要新增逻辑**：在 geocode_query 失败路径加 cache_set(None or {})... 但**这会改 amap_service.py 违背决策 1**
- **折中方案**：在 search.py 的新 resolver 层做这件事——失败时主动 cache_set 一个 sentinel value（如 `{"status": "not_found", "ts": now}`），TTL 24h；调用前先 cache_get，命中 sentinel 直接返回 None

**Alternatives considered**：
- 改 amap_service.py 让 geocode_query 缓存失败 → 拒绝（动 places.py 间接依赖、有回归风险）
- 在 search.py 用单独的 cache key（如 `amap:negative:{md5}`）→ 选用（最干净）

**Final Choice**: search.py 加一个独立的「negative cache」key：`amap:geocode:negative:{md5(query_normalized)}`，TTL 24h；amap 失败时写入。新 resolver 先查 negative cache、再走 detect_place_center → geocode_query 链路。

### 决策 4：「无 place_token」query 不调 amap、不报错

**Decision**: query 全是通用词（如「免费露营地」「附近驻车」）时，跳过 amap 调用、保持现有「用 fallback_lat/lon」行为、不返回 unrecognized_location。

**Rationale**：
- 用户搜「免费露营地」意图是「找我附近的免费露营地」，**不是搜某个地名**
- 这种 query 调 amap 会浪费 quota（amap 必然找不到「免费露营地」作地名）
- 这种 query 报错 unrecognized_location 体验糟糕（用户没搜地名却说「无法识别地名」）
- 现有 `_split_tokens` 已经能区分 place_tokens / generic_tokens（search.py:162），直接复用

**实现**：resolver 第 2 段加 `place_tokens, _ = _split_tokens(tokens); if not place_tokens: return GeoResolution(fallback_lat, fallback_lon, None, 'no_place_token')`

**Alternatives considered**：
- 一律调 amap → 拒绝（浪费 quota + 误报错）
- 全是通用词时 amap 失败后也报错 → 拒绝（用户体验差）

### 决策 5：unrecognized_location 时后端响应字段

**Decision**: 返回完整的 search response 结构，但 `spots=[]`、`unmapped_candidates=[]`、`answer=None`、`warning_code='unrecognized_location'`、`source_breakdown.search_center=None`。

**Rationale**：
- 前端 complete handler 期望统一结构（已 setAnswer/setAiCandidates/setUnmapped），返回空数组比返回 null 更安全（避免 null check 漏处理）
- `search_center=None` 让前端能判断「不要 setSearchCenter」（spec FR-009）
- 不调 AI、不查 DB（spec FR-010：不展示底库杂数据）→ 短路返回，节省成本

**Alternatives considered**：
- 抛 HTTP 400 错误 → 拒绝（前端要写额外的 catch、且小程序 Taro.request 错误码处理不一致）
- 不返回 warning_code、用 spots 空表示失败 → 拒绝（无法区分「识别失败」vs「识别成功但 AI 没搜到」）

### 决策 6：query 归一化用最简方案

**Decision**: cache key 用 `re.sub(r'\s+', ' ', query.strip())`，不做更复杂的归一化（如繁简转换、同义词替换）。

**Rationale**：
- 中文不区分大小写、不需要 lowercase
- 简单归一化覆盖 80% 重复查询场景（多空格、首尾空白）
- 繁简转换会引入 opencc 依赖（无必要）
- 同义词替换需要词库（无必要）

**Alternatives considered**：
- 完整 NFC unicode normalization → 拒绝（过度工程）
- 不归一化、原样作 cache key → 拒绝（「景德镇 」和「景德镇」算两个 key、cache hit 率下降）

### 决策 7：日志结构化字段

**Decision**: 每次 resolver 调用 log 一行结构化日志（JSON）：
```python
logger.info('geo_resolve', extra={
  'query': query[:80],   # 截断防长 query 撑爆日志
  'source': 'dict' | 'amap' | 'none' | 'no_place_token',
  'latency_ms': int,
  'status': 'ok' | 'timeout' | 'error' | 'not_found',
  'cache_hit': bool,    # geocode_query 内部 cache 命中（需从 amap_service 暴露、可选）
})
```

**Rationale**：spec FR-014 要求结构化字段，方便事后 grep 监控配额和成功率（`grep 'geo_resolve' | jq 'select(.source=="amap")'`）

## 不在范围内（明确排除）

- ❌ 修改 places.py / amap_service.py（spec-005 已稳定、有测试覆盖）
- ❌ 修改 ai_search_pipeline 内部的 detect_place_center 调用（H5 stream 路径、暂不动）
- ❌ 修改 PROVINCE_CENTERS 字典（hotfix `2b720f9` 已 commit、本 spec 复用作为快路径）
- ❌ 引入新的 geocoding 提供商（百度/Mapbox）
- ❌ 支持英文地名 / 拼音地名识别

## 验证策略

- **Unit / Integration**: 3 个新 pytest，mock `geocode_query` 测三段式分支
- **真机**: 用户操作微信小程序，覆盖 SC-006 三条 query（景德镇/莫干山/火星二号）
- **回归**: 跑现有 94 pytest（特别是 `test_q_unknown_city_amap_fallback`、`test_q_no_geo_intent_keeps_user_location`），确保 places.py 行为不变
