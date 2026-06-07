# Implementation Plan: 搜索地理意图识别 amap geocoding 兜底

**Branch**: `017-amap-geo-fallback` | **Date**: 2026-05-23 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/017-amap-geo-fallback/spec.md`

## Summary

把 `places.py` 已有的 `amap geocoding` 兜底（spec-005 实现的 `geocode_query` 函数 + Redis 缓存）**接入 `search.py` 的 `unified_search`**——字典未命中时自动调 amap、amap 也识别不到时返回明确的 `warning_code='unrecognized_location'`，不悄悄 fallback 到杭州。前端处理新 warning_code、显示报错且不动地图视野。

**核心策略**：**最小变更工程师**思路——复用现有 `geocode_query`（已有 Redis 缓存 + 超时 + 失败处理），不动 `places.py`（spec-005 已稳定）；只在 `search.py` 加一个三段式 resolver、改 `unified_search` 调用方式。

## Technical Context

**Language/Version**: Python 3.9（后端、CommandLineTools framework Python + venv） / TypeScript 5（前端、Taro 4）

**Primary Dependencies**:
- 后端：FastAPI / httpx（已用、调 amap）/ Redis（已用、cache）/ asyncio
- 前端：Taro 4 + React 18（已用、不增加）

**Storage**:
- PostgreSQL + PostGIS：**不动**（amap geocoding 不入 DB）
- Redis：复用现有 `geocode_query:{md5}` cache key（amap_service.py:147，TTL 默认 7 天）

**Testing**: pytest（94 现有用例，加 3 个新用例覆盖 spec-017 三段式）

**Target Platform**:
- 后端：macOS dev（uvicorn `--host 0.0.0.0:8000`）+ 未来云服务器
- 前端：微信小程序（主，spec-017 核心场景） + H5（次，stream 路径不动）

**Project Type**: Web service + Mobile mini-app（Option 2 - Web application with frontend/backend）

**Performance Goals**:
- 字典快路径：< 50ms（不调 amap、in-memory dict 查询）
- amap 命中：P95 < 500ms（含 geocode_query 2s 内部 timeout + Redis cache 30ms）
- 缓存命中：< 30ms

**Constraints**:
- amap geocoding 超时 ≤ 3s（spec FR-004，复用 `GEOCODE_QUERY_TIMEOUT=2.0` 已足够）
- Redis 不可用时降级为「每次都调 amap」（cache_get 返回 None 时直接调 API，不阻塞）
- 不动 H5 stream 路径（避免 spec-016 真机已通过的逻辑被破坏）

**Scale/Scope**:
- 用户量：< 100 daily searches（早期产品）
- amap quota：高德个人开发者 5000 次/天，远超需求
- 中国大陆地名覆盖：~300 地级市 + ~2800 区县 + 几十万 POI（靠 amap 覆盖）

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

`.specify/memory/constitution.md` 当前为模板状态（未填写具体项目宪法），**无具体宪法条款可违反**。Gate Pass ✅。

## Project Structure

### Documentation (this feature)

```text
specs/017-amap-geo-fallback/
├── plan.md              # This file
├── spec.md              # Created by /speckit-specify
├── research.md          # Phase 0 (本 plan 产出)
├── data-model.md        # Phase 1 (本 plan 产出)
├── quickstart.md        # Phase 1 (本 plan 产出)
├── contracts/
│   └── search-api.md    # Phase 1：unified_search 响应 schema 增量
├── checklists/
│   └── requirements.md  # specify 阶段产出（已存在）
└── tasks.md             # 由 /speckit-tasks 产出
```

### Source Code (repository root)

```text
backend/
├── app/
│   ├── routers/
│   │   ├── search.py           # ★ 改：加 _resolve_search_center_for_query + 改 unified_search
│   │   ├── places.py           # 不动（spec-005 已稳定）
│   │   └── ...
│   └── services/
│       ├── ai_service.py       # 不动（PROVINCE_CENTERS 字典 hotfix 已 commit 2b720f9）
│       └── amap_service.py     # 不动（geocode_query 复用 spec-005 实现）
└── tests/
    └── test_search_geo_fallback.py   # ★ 新增：3 个 case 覆盖字典/amap/unrecognized

frontend/src/
├── pages/index/index.tsx       # ★ 改：complete 事件处理 warning_code='unrecognized_location'
├── components/AnswerPanel.tsx   # 可能改：根据 warning_code 显示不同文案
├── types.ts                    # ★ 改：WarningCode 类型加 'unrecognized_location'
└── ...
```

**Structure Decision**: Option 2 Web application（已有结构、不新增目录）。

## Architecture: 三段式 resolver

新增 `_resolve_search_center_for_query(query, fallback_lat, fallback_lon) -> GeoResolution`：

```text
┌─────────────────────────────────────────────────────┐
│ query: "景德镇露营地"                                  │
└───────────────────────────┬─────────────────────────┘
                            ↓
              ┌─────────────────────────┐
              │ 1. 字典快路径            │
              │ detect_place_center()   │
              │ PROVINCE_CENTERS 命中？  │
              └────────┬─────────┬──────┘
                  命中 │         │ 未命中
                       ↓         ↓
              source=dict   ┌──────────────┐
              return        │ 2. 检查是否有  │
                            │ place_token   │
                            │ (非全是通用词) │
                            └──┬───────┬────┘
                            是 │       │ 否 (如「免费露营地」)
                               ↓       ↓
                    ┌──────────────┐  fallback to 用户位置
                    │ 3. amap 兜底  │  source=no_place_token
                    │ geocode_query │  return
                    │ (timeout 2s)  │
                    └──┬─────────┬──┘
                  命中 │         │ 未命中/timeout/error
                       ↓         ↓
              source=amap    source=none
              return        return (FR-007:
                            不 fallback 坐标!)
```

**关键区别 vs places.py 现有 `_resolve_search_center`**：
- places.py 第 3 段 fallback 到用户位置（保持原行为）
- search.py 新版第 3 段**明确报错**（spec FR-007、用户决策）

## Phase 0: Outline & Research

详见 [research.md](research.md)：
- 复用 vs 重写 amap 调用层的权衡
- Redis cache TTL（7 天 vs 24 小时）的取舍
- `unrecognized_location` 错误响应的字段设计
- `_split_tokens` 在「无 place_token」时的行为（避免「免费露营地」误报错）

## Phase 1: Design & Contracts

- [data-model.md](data-model.md)：GeoResolution dataclass / WarningCode 枚举扩展
- [contracts/search-api.md](contracts/search-api.md)：`POST /api/v1/search` 响应增量（warning_code='unrecognized_location' 时各字段值）
- [quickstart.md](quickstart.md)：开发期验证 spec-017 的 5 步骤（curl 三种 case + 前端真机）

## Complexity Tracking

> 无 Constitution violations，本节空。
