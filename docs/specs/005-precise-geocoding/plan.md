# Implementation Plan: 治本路径

**Branch**: main | **Date**: 2026-05-19 | **Spec**: [spec.md](./spec.md)

## Summary

两件事：
1. **AI prompt + 后端兜底**：地址只到城市级 → 进 unmapped（不让它进 geocode 流程）
2. **geocode_query 加 city/province hint**：消除「莫干山」类同名地歧义

代码动两个文件：`ai_service.py` + `amap_service.py`，约 30 行。

## Architecture

### 改动 1：`amap_service.py / geocode_query` 加 hint 参数

```python
async def geocode_query(
    q: str | None,
    *,
    city: str | None = None,         # 新增（可选）
    province: str | None = None,     # 新增（可选）
) -> tuple[float, float, str] | None:
    ...
    params = {"key": key, "address": q, "output": "json"}
    if city:
        params["city"] = city  # 高德支持 city 参数限定搜索范围
    ...
```

### 改动 2：`places.py / _resolve_search_center` 传 hint

```python
# 在调 geocode_query(q) 之前推断 province
inferred_province = _infer_province_from_text(q)  # 复用 ai_service 里的函数
amap_result = await geocode_query(q, province=inferred_province)
```

### 改动 3：`ai_service.py / normalize_candidates` 加"地址精度判断"

```python
# 在 line 1077 附近，try float(lat/lon) 之前：
address_hint = clean_text(raw.get("address_hint") or "")
if not _is_precise_address(address_hint):
    # 进 unmapped，不进 spots
    unmapped.append({...})
    continue
```

加辅助函数 `_is_precise_address(text) -> bool`：
- True：包含街道/路/号/村/镇/景区/营地名等关键词
- False：只含城市/省份/区域级词，或为空

### 改动 4：`ai_service.py` AI prompt 加新 rule

```python
"rules": [
    ...
    "address_hint 必须包含街道/路/号/村/镇/景区具体位置；只到城市级（如'上海'）就放 unmapped_candidates 而不是 spots",
]
```

## Tasks（TDD 流程）

- **T001** 写测试 `test_is_precise_address`（5 个用例覆盖 city-only / street / 空 / 边界）
- **T002** 实现 `_is_precise_address(text)` 函数 → T001 pass
- **T003** 写测试 `test_normalize_candidates_drops_city_only_spot` → fail
- **T004** 改 `normalize_candidates` 加 `_is_precise_address` 过滤 → T003 pass
- **T005** 写测试 `test_geocode_query_with_city_hint`（mock httpx，断言 params 含 city） → fail
- **T006** 改 `geocode_query` 加 city/province 参数 → T005 pass
- **T007** 改 `places.py / _resolve_search_center` 推断省份传给 geocode_query
- **T008** AI prompt 加新 rule（rules 数组追加 1 行）
- **T009** 跑全量 pytest 0 回归
- **T010** commit + 重启后端

## Risks

| 风险 | 缓解 |
|---|---|
| `_is_precise_address` 误判（把精确地址当模糊筛掉）| 用宽松判断：含**任一**街道关键词就算精确 |
| AI 不遵守新 prompt rule | 后端兜底 `_is_precise_address` 不依赖 AI 配合 |
| 高德 city 参数名拼写错（用 city/cityname/citys） | 看 spec 002 已经成功的调用确认是 `city` |
| 现有 spot 数据库 confidence=medium 大量是 city-only 错混进 | 不动旧数据（spec 004 已过滤）|

## Rollback

`git revert` 单 commit。

## Constitution Check

跳过；遵守 CLAUDE.md「4 件套」。

可以进入 implement。
