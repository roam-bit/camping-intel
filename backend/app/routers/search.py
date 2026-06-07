"""统一搜索入口 /api/v1/search

实现 V2 召回策略 B（DB-first + AI 兜底）：

1. 接收用户 query + 位置 + 半径 + limit
2. 先按关键词在 DB 检索：name + ai_summary + positive_summary 的 ILIKE（D6-1 = B）
3. 应用层 haversine 过滤距离（D6-4 = A，POC 不动 PostGIS）
4. 命中数 ≥ ceil(limit * 0.5)：直接返回 DB 结果（D6-2 = B）
5. 命中不足：调 AI 联网，与 DB 命中合并去重，AI 候选自动入库

输出形态与 /api/v1/ai/search 一致（前端可平滑替换），多一个 source_breakdown 字段
标明 DB 命中 / AI 新增 数量。
"""
from __future__ import annotations

import hashlib
import math
import re
import time
from dataclasses import dataclass
from typing import Any, Literal

import jieba
from fastapi import APIRouter, Depends
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.place import Place
from app.routers.places import haversine_km, is_displayable_place, place_to_dict
from app.schemas.place import SearchRequest
from app.services.ai_service import PROVINCE_CENTERS, ZHEJIANG_COORDS, _infer_province_from_text, ai_search_pipeline
from app.services.amap_service import geocode_query
from app.services.cache import cache_get, cache_set
from app.utils.logger import get_logger

logger = get_logger(__name__)


# ─────────────── spec-017: 地理意图三段式解析（字典 → amap → unrecognized）───────────────

GeoSource = Literal["dict", "amap", "no_place_token", "none"]


@dataclass(frozen=True)
class GeoResolution:
    """spec-017 三段式 search center 解析结果（不暴露到 API、仅 unified_search 内部用）。

    - source='dict'：PROVINCE_CENTERS/ZHEJIANG_COORDS 命中（快路径）
    - source='amap'：amap geocoding 命中（外网兜底）
    - source='no_place_token'：query 全是通用词（如"免费露营地"），跳过 amap、用 fallback、**不报错**
    - source='none'：字典 + amap 都识别不到、用户输入了地名但识别失败 → 触发 unrecognized_location
    """
    lat: float | None
    lon: float | None
    formatted_name: str | None
    source: GeoSource
    latency_ms: int
    cache_hit: bool = False


_AMAP_NEGATIVE_CACHE_PREFIX = "amap:geocode:negative:"
_AMAP_NEGATIVE_CACHE_TTL = 86400  # 24h（spec FR-005：失败也缓存避免反复调 amap）


def _normalize_query(q: str) -> str:
    """归一化 query 作为 cache key 输入。

    规则：trim 首尾空白 + 连续空白合一；保留中文原文、不 lowercase（中文无大小写）。
    例：「景德镇   露营地 」→「景德镇 露营地」
    """
    return re.sub(r"\s+", " ", q.strip())


async def _amap_negative_cache_get(query_normalized: str) -> bool:
    """检查 query 是否在 amap "识别失败" 的 negative cache 里。

    命中（True）表示 24h 内 amap 已确认识别不出来、不要重复调 amap。
    """
    key = f"{_AMAP_NEGATIVE_CACHE_PREFIX}{hashlib.md5(query_normalized.encode('utf-8')).hexdigest()}"
    value = await cache_get(key)
    return value is not None


async def _amap_negative_cache_set(query_normalized: str) -> None:
    """把 amap 识别失败的 query 写入 negative cache，TTL 24h。"""
    key = f"{_AMAP_NEGATIVE_CACHE_PREFIX}{hashlib.md5(query_normalized.encode('utf-8')).hexdigest()}"
    await cache_set(key, {"status": "not_found"}, ttl_seconds=_AMAP_NEGATIVE_CACHE_TTL)


router = APIRouter(prefix="/api/v1", tags=["search"])


def detect_place_center(query: str, tokens: list[str]) -> tuple[float, float, str] | None:
    """识别 query 中的已知地名，返回 (lat, lon, matched_name)。

    例：query="淳安农家乐露营" → ("淳安", 29.6088, 119.0431)
        query="莫干山附近营地" → ("莫干山", 30.6238, 119.9012)
        query="塔克拉玛干床车" → ("乌鲁木齐", 43.83, 87.62)（新疆中心）

    匹配顺序：
      1. ZHEJIANG_COORDS token 精确匹配（最细：淳安/莫干山等）
      2. PROVINCE_CENTERS token 精确匹配（其他省级地名）
      3. ZHEJIANG_COORDS substring 匹配（query 含浙江地名）
      4. PROVINCE_CENTERS substring 匹配（query 含其他省市地名）

    优先用更具体的地名（"杭州市" > "杭州"；"淳安县" > "淳安"）。
    """
    # 1) token 精确匹配（浙江细分 → 其他省份）
    for token in tokens:
        if token in ZHEJIANG_COORDS:
            lat, lon = ZHEJIANG_COORDS[token]
            return lat, lon, token
    for token in tokens:
        if token in PROVINCE_CENTERS:
            lat, lon = PROVINCE_CENTERS[token]
            return lat, lon, token
    # 2) substring 匹配，长名优先
    for name, (lat, lon) in sorted(ZHEJIANG_COORDS.items(), key=lambda x: len(x[0]), reverse=True):
        if name in query:
            return lat, lon, name
    for name, (lat, lon) in sorted(PROVINCE_CENTERS.items(), key=lambda x: len(x[0]), reverse=True):
        if name in query:
            return lat, lon, name
    # 3) 兜底：用 _infer_province_from_text 推断省份（覆盖「塔克拉玛干」「雅鲁藏布」「珠峰」
    #    等无字面省名但有强地理特征的关键词）→ 落到对应省级中心坐标
    inferred_province = _infer_province_from_text(query)
    if inferred_province and inferred_province in PROVINCE_CENTERS:
        lat, lon = PROVINCE_CENTERS[inferred_province]
        return lat, lon, inferred_province
    return None

# 预热 jieba 词典（首次调用会加载词典 ~3s，提前加载避免影响首次请求）
jieba.initialize()

# 停用词：常出现于自然语言但无信息量，丢掉避免噪声匹配
_STOP_TOKENS = {
    "的", "了", "是", "在", "有", "和", "或", "及", "与",
    "我", "你", "请", "想", "要", "找",
    "我想", "帮我", "可以", "希望", "应该", "推荐",
    "地方", "哪里", "哪些", "有哪些",
    "今晚", "明天", "周末", "怎么",
    "找一下", "找一找", "搜一下", "请问",
}

# 通用领域词：是用户 query 的高频功能词，但**信息量低**——几乎所有 POI 描述里都会出现。
# 这些 token 单独命中不应触发 DB hit；必须配合"地名词"或主题词才算相关。
# 例：「云南香格里拉露营」里的"露营"不应该让"杭州周边任何含露营的点位"被召回。
_GENERIC_DOMAIN_TOKENS = {
    "露营", "野外", "野外露营", "野营",
    "驻车", "驻车点", "停车", "停车场", "床车", "房车",
    "营地", "公共营地", "商业营地",
    "过夜", "夜宿",
    "自驾", "自驾游", "穷游", "户外",
    "免费", "低价", "收费",
    "周边", "附近",
    "厕所", "卫生间", "水源", "充电",
}


def _tokenize(query: str) -> list[str]:
    """从自然语言 query 抽取关键词。

    用 jieba 分词，过滤短词和停用词。
    例：「武夷山自驾露营」→ ["武夷山", "自驾", "露营"]
    """
    if not query:
        return []
    raw = jieba.lcut(query.strip())
    tokens: list[str] = []
    for token in raw:
        token = token.strip()
        if not token:
            continue
        if len(token) < 2:
            continue
        if token in _STOP_TOKENS:
            continue
        # 跳过纯标点/空白（jieba 偶尔返回）
        if not any(ch.isalnum() or "一" <= ch <= "龥" for ch in token):
            continue
        tokens.append(token)
    # 去重保序
    return list(dict.fromkeys(tokens))


def _split_tokens(tokens: list[str]) -> tuple[list[str], list[str]]:
    """把 token 拆成「高信息量 tokens」和「通用领域 tokens」。

    高信息量 = 地名 / 主题词 / 用户输入的具体描述（非通用词）
    通用领域 = 露营/驻车/营地 这类几乎所有点位都含的词

    Returns: (place_or_specific_tokens, generic_tokens)
    """
    place_tokens = [t for t in tokens if t not in _GENERIC_DOMAIN_TOKENS]
    generic_tokens = [t for t in tokens if t in _GENERIC_DOMAIN_TOKENS]
    return place_tokens, generic_tokens


async def search_db_by_keywords(
    db: AsyncSession,
    query: str,
    lat: float,
    lon: float,
    radius_km: float,
    limit: int,
) -> list[tuple[Place, float, int]]:
    """按关键词在 DB 检索，返回 [(place, distance_km, match_count)]，按相关性排序。

    关键规则（相关性把关）：
    1. 把 token 拆成「地名/主题词」(place_tokens) 和「通用领域词」(generic_tokens：露营/驻车 等)
    2. 如果 query 有 place_tokens：DB 命中必须**至少含一个 place_token**——通用词单独命中不算
       这避免「云南香格里拉露营」误召回一堆杭州含"露营"的点位
    3. 如果 query 全是通用词（如「免费露营地」）：保持 OR-all 行为，让用户基于地理范围找
    """
    tokens = _tokenize(query)
    if not tokens:
        return []

    place_tokens, generic_tokens = _split_tokens(tokens)

    # 决定 DB 查询的硬约束 token：优先 place_tokens；没有则 fallback 所有 token
    required_tokens = place_tokens if place_tokens else tokens

    token_conditions = []
    for token in required_tokens:
        pattern = f"%{token}%"
        token_conditions.append(
            or_(
                Place.name.ilike(pattern),
                Place.ai_summary.ilike(pattern),
                Place.positive_summary.ilike(pattern),
            )
        )

    # 整体：至少一个 required_token 命中（OR）。
    # 这意味着 query 含 place_tokens 时，DB 必须有 place_token 命中，光含"露营"等通用词不算。
    stmt = (
        select(Place)
        .options(selectinload(Place.sources))
        .where(
            Place.status.in_(["active", "pending_review"]),
            or_(*token_conditions),
        )
        .limit(300)  # 预筛宽口，后面再做距离 + 排序
    )
    rows = (await db.execute(stmt)).scalars().all()

    # 应用层 haversine 距离过滤 + 算 match_count（用全部 token 算相关性分）
    results: list[tuple[Place, float, int]] = []
    for place in rows:
        if not is_displayable_place(place):
            continue
        distance = haversine_km(lat, lon, place.latitude, place.longitude)
        if distance > radius_km:
            continue
        haystack = f"{place.name or ''} {place.ai_summary or ''} {place.positive_summary or ''}"
        # 安全网：再次确认 required_token 真的命中（ILIKE 大小写不敏感 vs in 大小写敏感）
        required_hits = sum(1 for token in required_tokens if token in haystack)
        if required_hits == 0:
            continue
        # match_count 用全部 token 计算（含通用词），用于排序——同一个地点出现的 token 越多越相关
        match_count = sum(1 for token in tokens if token in haystack)
        results.append((place, distance, match_count))

    # 排序：命中 token 多优先 → 可信度高优先 → 距离近优先
    results.sort(key=lambda item: (-item[2], -item[0].credibility_score, item[1]))
    return results[:limit]


def _empty_metrics_block(cache_hit: bool, elapsed_seconds: float | None = None) -> dict[str, Any]:
    return {
        "cache_hit": cache_hit,
        "model_id": None,
        "elapsed_seconds": {"search": None, "extract": None, "total": elapsed_seconds},
        "tokens": {
            "input": None,
            "output": None,
            "search_input": None,
            "search_output": None,
            "extract_input": None,
            "extract_output": None,
        },
        "cost_cny": 0.0,
    }


async def _resolve_search_center_for_query(
    query: str,
    fallback_lat: float,
    fallback_lon: float,
) -> GeoResolution:
    """spec-017 三段式：字典 → amap → unrecognized。

    与 places.py 的 _resolve_search_center 不同：
    - amap 失败时**不** fallback 用户位置（spec FR-007，明确报错让用户知情）
    - 用 source='none' 区分「真的识别不到」vs「没在搜地名」（source='no_place_token'）

    场景分支：
    1. 空 query / 无 strip 内容 → source='no_place_token'（保持原行为）
    2. 字典命中（PROVINCE_CENTERS 等）→ source='dict'（快路径、不调 amap）
    3. query 全是通用词（如"免费露营地"）→ source='no_place_token'（用 fallback、不报错）
    4. negative cache 命中 → source='none'（24h 内已知识别不到、直接报 unrecognized）
    5. amap geocoding 命中 → source='amap'
    6. amap 失败/超时/无结果 → source='none' + 写 negative cache
    """
    t0 = time.perf_counter()

    # 场景 1：空 query
    if not query or not query.strip():
        return GeoResolution(
            lat=fallback_lat,
            lon=fallback_lon,
            formatted_name=None,
            source="no_place_token",
            latency_ms=int((time.perf_counter() - t0) * 1000),
        )

    tokens = _tokenize(query)

    # 场景 2：字典快路径（PROVINCE_CENTERS / ZHEJIANG_COORDS）
    detected = detect_place_center(query, tokens)
    if detected:
        lat, lon, name = detected
        # spec-017 hardening：detect_place_center 的第 3 步 _infer_province_from_text
        # 命中"省级关键词"时只会返回省级中心坐标（如「盐城露营地」→「江苏省」→ 南京坐标）。
        # 这丢失了城市级精度——用户搜「盐城」期望去盐城、而不是 250km 外的南京。
        # 检测到 detected name 是省级名 → 用 amap 精化拿城市级坐标。
        _is_province_level = (
            name.endswith("省")
            or name.endswith("自治区")
            or name in {"北京市", "上海市", "天津市", "重庆市"}
        )
        if _is_province_level:
            try:
                amap_refined = await geocode_query(query)
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "geo_resolve.province_refine_failed",
                    extra={"query": query[:80], "err": str(exc)[:120]},
                )
                amap_refined = None
            # 复用 amap 软成功检测：refined name 必须含 query 的某个 token
            tokens_for_check = [t for t in tokens if t not in _GENERIC_DOMAIN_TOKENS] or tokens
            if amap_refined is not None and any(t in amap_refined[2] for t in tokens_for_check):
                latency_ms = int((time.perf_counter() - t0) * 1000)
                logger.info(
                    "geo_resolve",
                    extra={
                        "query": query[:80],
                        "source": "amap",
                        "latency_ms": latency_ms,
                        "cache_hit": False,
                        "status": "ok",
                        "refined_from_province": name,
                    },
                )
                return GeoResolution(
                    lat=amap_refined[0], lon=amap_refined[1], formatted_name=amap_refined[2],
                    source="amap", latency_ms=latency_ms,
                )
            # amap 精化失败 → fallback 用省级中心（保持原行为，不退化）
        latency_ms = int((time.perf_counter() - t0) * 1000)
        logger.info(
            "geo_resolve",
            extra={
                "query": query[:80],
                "source": "dict",
                "latency_ms": latency_ms,
                "cache_hit": False,
                "status": "ok",
            },
        )
        return GeoResolution(
            lat=lat, lon=lon, formatted_name=name,
            source="dict", latency_ms=latency_ms,
        )

    # 场景 3：全是通用词（如"免费露营地"）→ 用 fallback、不调 amap、不报错
    place_tokens, _ = _split_tokens(tokens)
    if not place_tokens:
        latency_ms = int((time.perf_counter() - t0) * 1000)
        logger.info(
            "geo_resolve",
            extra={
                "query": query[:80],
                "source": "no_place_token",
                "latency_ms": latency_ms,
                "cache_hit": False,
                "status": "ok",
            },
        )
        return GeoResolution(
            lat=fallback_lat, lon=fallback_lon, formatted_name=None,
            source="no_place_token", latency_ms=latency_ms,
        )

    # 场景 4：negative cache 命中（24h 内已知 amap 也识别不到）
    normalized = _normalize_query(query)
    if await _amap_negative_cache_get(normalized):
        latency_ms = int((time.perf_counter() - t0) * 1000)
        logger.info(
            "geo_resolve",
            extra={
                "query": query[:80],
                "source": "none",
                "latency_ms": latency_ms,
                "cache_hit": True,
                "status": "not_found",
            },
        )
        return GeoResolution(
            lat=None, lon=None, formatted_name=None,
            source="none", latency_ms=latency_ms, cache_hit=True,
        )

    # 场景 5/6：调 amap geocoding（geocode_query 内部已有 7 天 cache + 2s timeout + 失败返回 None）
    amap_result: tuple[float, float, str] | None = None
    amap_status = "ok"
    try:
        amap_result = await geocode_query(query)
    except Exception as exc:  # noqa: BLE001 — amap 任何异常都视为识别失败
        amap_status = "error"
        logger.warning(
            "geo_resolve.amap_exception",
            extra={"query": query[:80], "err_type": type(exc).__name__, "err": str(exc)[:120]},
        )

    latency_ms = int((time.perf_counter() - t0) * 1000)

    if amap_result is not None:
        lat, lon, name = amap_result
        # spec-017 hardening：amap 对乱码/不存在地名会返回模糊匹配的远端坐标（如「火星二号营地」→
        # 贵州凯里火星，「zxcvbnm营地」→ 河北唐山）。这种「软成功」会把用户误导到无关位置。
        # 强校验：amap formatted_name 必须包含 query 的至少一个 place_token，否则视为软成功 → unrecognized
        if not any(t in name for t in place_tokens):
            await _amap_negative_cache_set(normalized)
            logger.info(
                "geo_resolve",
                extra={
                    "query": query[:80],
                    "source": "none",
                    "latency_ms": latency_ms,
                    "cache_hit": False,
                    "status": "soft_miss",
                    "amap_returned": name[:80],
                },
            )
            return GeoResolution(
                lat=None, lon=None, formatted_name=None,
                source="none", latency_ms=latency_ms,
            )
        logger.info(
            "geo_resolve",
            extra={
                "query": query[:80],
                "source": "amap",
                "latency_ms": latency_ms,
                "cache_hit": False,
                "status": "ok",
            },
        )
        return GeoResolution(
            lat=lat, lon=lon, formatted_name=name,
            source="amap", latency_ms=latency_ms,
        )

    # amap 也识别不到 → 写 negative cache + 返回 source='none'
    await _amap_negative_cache_set(normalized)
    logger.info(
        "geo_resolve",
        extra={
            "query": query[:80],
            "source": "none",
            "latency_ms": latency_ms,
            "cache_hit": False,
            "status": "not_found" if amap_status == "ok" else amap_status,
        },
    )
    return GeoResolution(
        lat=None, lon=None, formatted_name=None,
        source="none", latency_ms=latency_ms,
    )


def _build_unrecognized_location_response(query: str, threshold: int, elapsed_s: float) -> dict[str, Any]:
    """spec-017 FR-006/007/010: amap 也识别不到时的明确错误响应。

    特点：
    - search_center=None：前端契约「不动地图视野」
    - spots/unmapped_candidates=[]：不展示底库杂数据
    - 不调 AI / 不查 DB：成本 0、provider.llm='none'
    """
    return {
        "answer": None,
        "spots": [],
        "unmapped_candidates": [],
        "sources": [],
        "warning": (
            f"无法识别您输入的地名「{query}」，"
            "请尝试更明确的地名（如「南昌露营地」「莫干山民宿」）"
        ),
        "warning_code": "unrecognized_location",
        "provider": {"llm": "none", "model": "none", "search": "none", "map": "amap"},
        "cache": {"hit": False, "reason": "unrecognized_location"},
        "metrics": _empty_metrics_block(cache_hit=False, elapsed_seconds=elapsed_s),
        "extract_pending": False,
        "extract_cache_key": None,
        "source_breakdown": {
            "db": 0,
            "ai": 0,
            "threshold": threshold,
            "strategy": "unrecognized_location",
            "detected_place": None,
            "search_center": None,
            "search_center_source": "none",
        },
    }


@router.post("/search")
async def unified_search(payload: SearchRequest, db: AsyncSession = Depends(get_db)) -> dict[str, Any]:
    """统一搜索：DB 命中足够直接返回，不够再调 AI 兜底。"""
    start_t = time.perf_counter()

    # 阈值：limit × 50%，至少 1 条
    threshold = max(1, math.ceil(payload.limit * 0.5))

    # spec-017: 三段式地理意图识别（字典 → amap → unrecognized）
    resolution = await _resolve_search_center_for_query(
        payload.q, payload.lat, payload.lon,
    )

    # spec-017 FR-006/007: amap 也识别不到 → 明确报错短路返回，不调 AI、不查 DB
    if resolution.source == "none":
        elapsed = round(time.perf_counter() - start_t, 3)
        return _build_unrecognized_location_response(payload.q, threshold, elapsed)

    effective_lat = resolution.lat if resolution.lat is not None else payload.lat
    effective_lon = resolution.lon if resolution.lon is not None else payload.lon
    detected_name = resolution.formatted_name

    # Step 1: DB 关键词检索
    db_hits = await search_db_by_keywords(
        db,
        query=payload.q,
        lat=effective_lat,
        lon=effective_lon,
        radius_km=payload.radius_km,
        limit=max(payload.limit, threshold),
    )

    db_hit_count = len(db_hits)
    elapsed_db = round(time.perf_counter() - start_t, 3)

    # Step 2: 命中 ≥ 阈值，直接返回不调 AI
    if db_hit_count >= threshold:
        spots = [
            place_to_dict(place, distance_km=distance)
            for place, distance, _ in db_hits[: payload.limit]
        ]
        return {
            "answer": None,
            "spots": spots,
            "unmapped_candidates": [],
            "sources": [],
            "warning": None,
            "warning_code": None,
            "provider": {
                "llm": "db_only",
                "model": "none",
                "search": "db_keyword",
                "map": "amap",
            },
            "cache": {"hit": True, "reason": "db_threshold_met"},
            "metrics": _empty_metrics_block(cache_hit=True, elapsed_seconds=elapsed_db),
            "source_breakdown": {
                "db": db_hit_count,
                "ai": 0,
                "threshold": threshold,
                "strategy": "db_only",
                "detected_place": detected_name,
                "search_center": {"lat": effective_lat, "lon": effective_lon},
                "search_center_source": resolution.source,  # spec-017: 'dict'/'amap'/'no_place_token'
            },
        }

    # Step 3: 命中不足，调 AI 补
    ai_response = await ai_search_pipeline(
        db,
        query=payload.q,
        limit=payload.limit,
        radius_km=int(payload.radius_km),
    )

    ai_spots = ai_response.get("spots") or []

    # Step 4: 合并 DB 命中 + AI 新候选，去重（按 id）
    seen_ids: set[str] = set()
    merged: list[dict[str, Any]] = []

    for place, distance, _ in db_hits:
        place_dict = place_to_dict(place, distance_km=distance)
        pid = place_dict.get("id")
        if pid and pid not in seen_ids:
            merged.append(place_dict)
            seen_ids.add(pid)

    # spec-017 真机暴露的 bug：AI extract 偶尔返回坐标错乱的 spot（如「连云港海滨国家森林公园」
    # 实际坐标在 (31.59, 120.25) = 太湖附近、距连云港 348km）。需要按 radius_km 过滤、
    # 不能让远超范围的脏坐标 marker 落到地图上误导用户。
    ai_spots_filtered = []
    ai_spots_dropped_far = 0
    for spot in ai_spots:
        spot_lat = spot.get("latitude")
        spot_lon = spot.get("longitude")
        if spot_lat is None or spot_lon is None:
            ai_spots_filtered.append(spot)  # 没坐标的不知道距离、保守保留（不该出现，留个口子）
            continue
        try:
            dist = haversine_km(effective_lat, effective_lon, float(spot_lat), float(spot_lon))
        except (TypeError, ValueError):
            ai_spots_filtered.append(spot)
            continue
        if dist > payload.radius_km:
            ai_spots_dropped_far += 1
            logger.info(
                "ai_spot_dropped_far",
                extra={
                    "spot_name": (spot.get("name") or "")[:60],
                    "spot_coord": (spot_lat, spot_lon),
                    "search_center": (effective_lat, effective_lon),
                    "distance_km": round(dist, 1),
                    "radius_km": payload.radius_km,
                },
            )
            continue
        ai_spots_filtered.append(spot)

    for spot in ai_spots_filtered:
        sid = spot.get("id")
        if sid and sid not in seen_ids:
            merged.append(spot)
            seen_ids.add(sid)

    merged = merged[: payload.limit]

    elapsed_total = round(time.perf_counter() - start_t, 3)
    ai_metrics = ai_response.get("metrics") or _empty_metrics_block(cache_hit=False)
    # 覆盖 total elapsed 为整个 /search 的耗时（含 DB 查询）
    ai_metrics = dict(ai_metrics)
    if isinstance(ai_metrics.get("elapsed_seconds"), dict):
        ai_metrics["elapsed_seconds"] = {
            **ai_metrics["elapsed_seconds"],
            "total": elapsed_total,
            "db_query": elapsed_db,
        }
    else:
        ai_metrics["elapsed_seconds"] = {
            "search": None,
            "extract": None,
            "db_query": elapsed_db,
            "total": elapsed_total,
        }

    return {
        **ai_response,
        "spots": merged,
        "metrics": ai_metrics,
        "source_breakdown": {
            "db": db_hit_count,
            "ai": len(ai_spots),
            "threshold": threshold,
            "strategy": "db_plus_ai",
            "detected_place": detected_name,
            "search_center": {"lat": effective_lat, "lon": effective_lon},
            "search_center_source": resolution.source,  # spec-017: 'dict'/'amap'/'no_place_token'
        },
    }
