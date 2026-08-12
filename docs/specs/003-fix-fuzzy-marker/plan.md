# Implementation Plan: 模糊位置点位不出 marker

**Branch**: main | **Date**: 2026-05-18 | **Spec**: [spec.md](./spec.md)

## Summary

`ai_service.py` line 1099-1121 改：geocode 失败 / confidence=low 时把 spot 加进 `unmapped_candidates` 并 `continue`，不再生成 fake marker。

## Architecture

只动 1 个文件 `backend/app/services/ai_service.py`，约 15 行改动。

### 改动前（现状）

```python
geo = await geocode_with_amap(name, ...)
if geo:
    lat, lon = geo["lat"], geo["lon"]   # 精确坐标 ✅
else:
    lat, lon = spread_approximate_coord(*fallback_center(...), ...)  # ⚠️ 这就是江里 marker 的来源
    location_confidence = "low"
# 接下来 line 1229: place = Place(name=..., latitude=lat, longitude=lon)  ← 所有 spot 都进 places
```

### 改动后

```python
geo = await geocode_with_amap(name, ...)
if geo and geo.get("confidence") in ("high", "medium"):
    lat, lon = geo["lat"], geo["lon"]
    # ...正常构造 Place
else:
    # 位置无法精确识别：加进 unmapped，不进 spots
    unmapped.append({
        "name": name,
        "address_hint": raw.get("address_hint"),
        "snippet_summary": clean_text(...),
        "reason": "位置无法精确识别（geocode level 过粗或失败）",
        "sources": [public_source(item) for item in linked],
    })
    continue  # 跳过 Place 创建
```

### TDD 任务

- **T001** 写测试 `test_spot_dropped_when_geocode_none`（mock geocode_with_amap = None）
- **T002** 写测试 `test_spot_dropped_when_confidence_low`
- **T003** 写测试 `test_spot_kept_when_confidence_high`（正常路径）
- **T004** 改代码使 T001-T003 pass
- **T005** 跑全量 pytest 0 回归
- **T006** commit

## Risks

| 风险 | 缓解 |
|---|---|
| 改动过多 spot 被筛 → 用户演示时 marker 太少 | 浏览器实测；如果太多被筛，把条件改成 confidence=low 才筛（不要把"未知"也筛） |
| 现有 fallback_center 逻辑有别处用到 | 只改 line 1099-1121 路径，不删 fallback_center 函数本身 |

## Rollback

`git revert` 单 commit。

## Constitution Check

跳过（项目 constitution 未填）；遵守 CLAUDE.md「4 件套」。

可以进入 implement。
