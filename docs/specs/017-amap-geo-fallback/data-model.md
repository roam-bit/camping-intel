# Phase 1 Data Model: spec-017

## 新增实体

### `GeoResolution` (后端 search.py 内部 dataclass)

Resolver 函数的返回结构、不暴露到 API。

```python
from dataclasses import dataclass
from typing import Literal

@dataclass(frozen=True)
class GeoResolution:
    """spec-017 三段式 search center 解析结果。"""
    lat: float | None        # 解析出的纬度；source='none' 时为 None
    lon: float | None        # 解析出的经度；source='none' 时为 None
    formatted_name: str | None  # detected_place 展示用名（如「江西省景德镇市」）
    source: Literal['dict', 'amap', 'none', 'no_place_token']
    latency_ms: int          # resolver 总耗时
    cache_hit: bool          # negative cache 命中标记（amap 失败 cache）
```

**字段语义**：
- `source='dict'`：字典命中（PROVINCE_CENTERS 或 ZHEJIANG_COORDS）；快路径
- `source='amap'`：amap geocoding 命中
- `source='no_place_token'`：query 全是通用词（如「免费露营地」），跳过 amap、用 fallback 坐标、**不算 unrecognized**
- `source='none'`：字典 + amap 都识别不到 → **触发 unrecognized_location**（用户输入了地名但识别失败）

**状态转换**：单次调用、无生命周期；结果由 cache 复用（amap 命中存 amap_service 现有 cache、失败存新 negative cache）。

## 现有响应字段扩展

### `unified_search` 响应（`POST /api/v1/search`）

无 schema 破坏性变更，仅扩展 `warning_code` 枚举值 + `source_breakdown` 在失败时的字段值。

#### 新增 `warning_code` 枚举值

```python
WarningCode = Literal[
    'extract_timeout',
    'extract_json_error',
    'extract_other',
    'network_error',
    'unrecognized_location',  # ★ spec-017 新增
]
```

#### `source_breakdown` 在 unrecognized_location 时

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
    "search_center": null
  },
  "extract_pending": false,
  "extract_cache_key": null,
  "cache": {"hit": false, "reason": "unrecognized_location"},
  "provider": {"llm": "none", "model": "none", "search": "none", "map": "amap"},
  "metrics": { ... }
}
```

**关键约束**（spec FR-007/009）：
- `search_center: null` — 前端检测到 null 时**不**调 `setSearchCenter`、地图视野保持不变
- `spots: []` + `unmapped_candidates: []` — 不展示任何点位（spec FR-010）
- `extract_pending: false` — 不启动 polling

### `source_breakdown` 在正常路径

无变化，但新增 `source` 字段标识哪段命中（调试用）：

```json
{
  "source_breakdown": {
    ...
    "search_center_source": "dict" | "amap" | "no_place_token"
  }
}
```

## Redis 缓存键

### 已有 key（geocode_query 内部，不动）

```
geocode_query:{md5(q|city|province)}
TTL: 默认（约 7 天）
Value: {"lat": float, "lon": float, "name": str}
```

### 新增 negative cache key（search.py spec-017）

```
amap:geocode:negative:{md5(query_normalized)}
TTL: 86400 (24h)
Value: {"status": "not_found", "ts": "2026-05-23T..."}
归一化规则: re.sub(r'\s+', ' ', query.strip())  # 不 lowercase、保留中文原文
```

**用途**：amap 也识别不到的 query 24h 内不重试调 amap，节省配额（spec FR-005）。

## 前端类型扩展

### `frontend/src/types.ts` 增量

```typescript
export type WarningCode =
  | 'extract_timeout'
  | 'extract_json_error'
  | 'extract_other'
  | 'network_error'
  | 'unrecognized_location'  // ★ spec-017
```

注意：当前 `warningCode` state 在 `index.tsx:74` 是 `useState<string | null>(null)`、未严格类型化。本 spec 不强制改 useState 类型（最小变更）、仅在判断处用字符串比较 `warningCode === 'unrecognized_location'`。

## 日志结构

```python
logger.info('geo_resolve', extra={
    'query': query[:80],              # 截断防长 query
    'source': resolution.source,
    'latency_ms': resolution.latency_ms,
    'cache_hit': resolution.cache_hit,
    'status': 'ok' | 'timeout' | 'error' | 'not_found',
})
```

Grep 示例：
```bash
# 监控 amap 调用成功率
grep 'geo_resolve' uvicorn.log | jq 'select(.source=="amap")' | jq '.status' | sort | uniq -c

# 监控 unrecognized 比例
grep 'geo_resolve' uvicorn.log | jq 'select(.source=="none")' | jq '.query'
```
