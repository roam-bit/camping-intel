# Contract: POST /api/v1/search （spec-017 增量）

本 spec 不引入新接口，仅扩展 `POST /api/v1/search` 的响应行为。

## 请求（无变化）

```http
POST /api/v1/search
Content-Type: application/json

{
  "q": "景德镇露营地",
  "limit": 12,
  "radius_km": 80,
  "lat": 30.27,
  "lon": 120.15
}
```

## 响应：3 种新场景

### Case 1: 字典命中（快路径，无 amap 调用）

**Trigger**：query 含字典词（如「南昌露营地」「莫干山民宿」「大庆露营地」）

```json
{
  "answer": { /* AI 整理结果 */ },
  "spots": [ /* AI 联网搜出来的点位 */ ],
  "unmapped_candidates": [...],
  "sources": [...],
  "warning": null,
  "warning_code": null,
  "source_breakdown": {
    "db": 0,
    "ai": 5,
    "threshold": 6,
    "strategy": "db_plus_ai",
    "detected_place": "南昌",
    "search_center": {"lat": 28.68, "lon": 115.86},
    "search_center_source": "dict"   ← ★ spec-017 新增
  },
  ...
}
```

**性能契约**：resolver 阶段 < 50ms（in-memory 字典查找）

---

### Case 2: amap 命中（字典 miss、amap fallback 成功）

**Trigger**：query 含字典外地名（如「景德镇露营地」「莫干山民宿」实际「莫干山」已在字典所以走 Case 1，举例「鄱阳湖露营」）

```json
{
  "answer": { /* AI 整理 */ },
  "spots": [...],
  "source_breakdown": {
    "db": 0,
    "ai": 3,
    "threshold": 6,
    "strategy": "db_plus_ai",
    "detected_place": "江西省九江市鄱阳县",   ← amap formatted_address
    "search_center": {"lat": 29.0, "lon": 116.7},
    "search_center_source": "amap"   ← ★ spec-017 新增
  },
  ...
}
```

**性能契约**：
- 缓存命中：< 30ms
- 缓存未命中 + amap 调用：P95 < 500ms（含 amap 2s 内部 timeout）

**幂等性**：同 query 24h 内重复调，第 1 次调 amap、之后 cache 命中（geocode_query 内部 7 天 cache）。

---

### Case 3: 字典 + amap 都识别不到（unrecognized_location）

**Trigger**：query 含「地名意图」但 amap 也找不到（如「火星二号营地」「赛博朋克镇驻车」）

```json
{
  "answer": null,
  "spots": [],
  "unmapped_candidates": [],
  "sources": [],
  "warning": "无法识别您输入的地名「火星二号营地」，请尝试更明确的地名（如「南昌露营地」「莫干山民宿」）",
  "warning_code": "unrecognized_location",
  "source_breakdown": {
    "db": 0,
    "ai": 0,
    "threshold": 6,
    "strategy": "unrecognized_location",
    "detected_place": null,
    "search_center": null,           ← ★ 关键：null 而非 fallback 杭州
    "search_center_source": "none"
  },
  "extract_pending": false,
  "extract_cache_key": null,
  "cache": {"hit": false, "reason": "unrecognized_location"},
  "provider": {"llm": "none", "model": "none", "search": "none", "map": "amap"},
  "metrics": {
    "cache_hit": false,
    "model_id": null,
    "elapsed_seconds": {"search": null, "extract": null, "total": 0.5},
    "tokens": {"input": 0, "output": 0, ...},
    "cost_cny": 0.0
  }
}
```

**关键不变量**：
- `search_center: null`（前端契约：检测到 null 不调 `setSearchCenter`）
- `spots: []` + `unmapped_candidates: []`（不展示任何点位）
- 不调 AI（成本为 0、`provider.llm = "none"`）
- 不查 DB（`source_breakdown.db = 0`）
- `extract_pending: false`（前端不启动 polling）

**幂等性**：同 query 24h 内重复调，第 1 次写 negative cache、之后命中 negative cache 直接返回（不调 amap）。

---

### Case 4: 无地名 token（如「免费露营地」，保持原行为）

**Trigger**：query 全是通用词（无 place_token）

```json
{
  "answer": { /* AI 用 user lat/lon 搜本地 */ },
  "spots": [...],
  "source_breakdown": {
    "detected_place": null,
    "search_center": {"lat": 30.27, "lon": 120.15},   ← user lat/lon
    "search_center_source": "no_place_token"
  },
  ...
}
```

**不触发** unrecognized_location（用户没在搜地名）。

## 兼容性

- ✅ 现有客户端不读 `source_breakdown.search_center_source` 字段时**不受影响**（新加字段、可忽略）
- ✅ 现有客户端不识别 `warning_code='unrecognized_location'` 时**仍能展示** `warning` 文案（fallback 路径正确）
- ⚠️ 客户端如果对 `search_center: null` 处理不当（如直接读 .lat 报错）需要 spec-017 一起改前端（已在 plan 中）

## 测试契约

| Test | Case | Mock | Expected |
|------|------|------|----------|
| `test_dict_hit_no_amap` | 1 | 不 mock | `source_breakdown.search_center_source == 'dict'`，amap 未被调用 |
| `test_amap_fallback_hit` | 2 | mock `geocode_query` → (29.0, 116.7, "...") | `search_center.lat ≈ 29.0`，`search_center_source == 'amap'` |
| `test_amap_fallback_miss` | 3 | mock `geocode_query` → None | `warning_code == 'unrecognized_location'`，`search_center is None`，`spots == []` |
| `test_no_place_token_keeps_user_loc` | 4 | 不 mock | `search_center.lat == 30.27`（user lat），无 warning |
| `test_amap_timeout` | 3 变种 | mock `geocode_query` raises TimeoutError | `warning_code == 'unrecognized_location'` |
| `test_negative_cache_hit` | 3 重复 | 第 1 次 mock None，第 2 次 cache 命中 | 第 2 次 amap 函数**未被调用**（cache_hit=True） |
