from __future__ import annotations

import math
import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from geoalchemy2 import Geography, WKTElement
from geoalchemy2.functions import ST_DWithin, ST_Distance, ST_MakePoint, ST_SetSRID
from sqlalchemy import cast, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.feedback import Feedback
from app.models.place import Place
from app.models.source import Source
from app.schemas.place import FeedbackIn, GeocodeRequest, SaveCandidateRequest
from app.services.ai_service import parse_source_date, public_fact_source_model, scrub_internal_source_text, scrub_risk_tags
from app.services.amap_service import geocode_query, geocode_with_amap
from app.services.credibility_service import calculate_credibility_score, days_since, recommendation_from_score

router = APIRouter(prefix="/api/v1/places", tags=["places"])
utility_router = APIRouter(prefix="/api/v1", tags=["geo"])

CATEGORY_TYPES = {
    "营地": ("营地", "camp_site", "caravan_site", "商业营地", "景区露营区"),
    "野外露营": ("野外", "公园", "水域", "沙滩", "草坪"),
    "驻车点": ("驻车", "停车", "床车"),
    "服务区": ("服务区",),
}


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return radius * 2 * math.asin(math.sqrt(a))


def source_date_for_display(source: Source) -> datetime | None:
    return source.source_time or parse_source_date(f"{source.title or ''} {source.snippet or ''}")


def latest_display_source_date(place: Place, sources: list[Source]) -> datetime | None:
    dates = [date for source in sources if (date := source_date_for_display(source))]
    for value in (place.ai_summary, place.positive_summary, place.negative_summary, place.source_summary):
        if date := parse_source_date(value):
            dates.append(date)
    return max(dates) if dates else None


def source_time_status_for_display(place: Place, sources: list[Source]) -> str:
    if not sources:
        return "unknown"
    if latest_display_source_date(place, sources):
        return "known"
    return "unknown"


def source_to_dict(source: Source) -> dict[str, Any]:
    source_date = source_date_for_display(source)
    return {
        "id": str(source.id),
        "source_type": source.source_type,
        "source_url": source.source_url,
        "domain": source.domain,
        "title": scrub_internal_source_text(source.title),
        "snippet": scrub_internal_source_text(source.snippet),
        "source_time": source_date.isoformat() if source_date else None,
        "reliability_score": source.reliability_score,
    }


def feedback_to_dict(feedback: Feedback) -> dict[str, Any]:
    return {
        "id": str(feedback.id),
        "can_park_now": feedback.can_park_now,
        "can_overnight": feedback.can_overnight,
        "price_status": feedback.price_status,
        "toilet_available": feedback.toilet_available,
        "was_warned": feedback.was_warned,
        "vehicle_type": feedback.vehicle_type,
        "comment": feedback.comment,
        "created_at": feedback.created_at.isoformat(),
    }


def public_geo_source(value: str | None) -> str | None:
    if not value:
        return value
    return "map_import" if value.lower().startswith("osm") else value


def public_data_origin(value: str | None) -> str | None:
    if not value:
        return value
    return "map_import" if "osm" in value.lower() else value


def fact_sources_for_place(place: Place) -> list[Source]:
    return [source for source in list(getattr(place, "sources", []) or []) if public_fact_source_model(source)]


def is_displayable_place(place: Place) -> bool:
    return bool(fact_sources_for_place(place))


def place_to_dict(place: Place, distance_km: float | None = None, detail: bool = False) -> dict[str, Any]:
    fact_sources = fact_sources_for_place(place) if "sources" in place.__dict__ else []
    source_count = len(fact_sources) if "sources" in place.__dict__ else place.source_count
    latest_source_date = latest_display_source_date(place, fact_sources) if "sources" in place.__dict__ else place.last_verified_at
    data = {
        "id": str(place.id),
        "name": place.name,
        "type": place.type,
        "latitude": place.latitude,
        "longitude": place.longitude,
        "address": place.address,
        "city": place.city,
        "district": place.district,
        "province": place.province,
        "location_confidence": place.location_confidence,
        "geo_source": public_geo_source(place.geo_source),
        "ai_rating": place.ai_rating,
        "credibility_score": place.credibility_score,
        "recommendation": place.recommendation,
        "source_count": source_count,
        "price_clues": place.price_clues or [],
        "overnight_clues": place.overnight_clues or [],
        "toilet_status": place.toilet_status,
        "water_status": place.water_status,
        "electricity_status": place.electricity_status,
        "height_limit": place.height_limit,
        "vehicle_fit": place.vehicle_fit or [],
        "risk_tags": scrub_risk_tags(place.risk_tags or [], bool(source_count)),
        "ai_summary": scrub_internal_source_text(place.ai_summary),
        "positive_summary": scrub_internal_source_text(place.positive_summary),
        "negative_summary": scrub_internal_source_text(place.negative_summary),
        "source_summary": scrub_internal_source_text(place.source_summary),
        "last_verified_at": place.last_verified_at.isoformat() if place.last_verified_at else None,
        "latest_source_date": latest_source_date.date().isoformat() if latest_source_date else None,
        "source_time_status": source_time_status_for_display(place, fact_sources) if "sources" in place.__dict__ else "unknown",
        "data_origin": public_data_origin(place.data_origin),
        "status": place.status,
        "updated_at": place.updated_at.isoformat(),
        "distance_km": round(distance_km, 1) if distance_km is not None else None,
    }
    if detail:
        data["sources"] = [source_to_dict(source) for source in fact_sources]
        data["feedbacks"] = [feedback_to_dict(feedback) for feedback in getattr(place, "feedbacks", [])]
        data["disclaimer"] = "本产品信息基于公开资料、用户反馈和 AI 整理生成，仅供出行参考。实际停车、露营、过夜需遵守当地法律法规及现场管理要求。"
    return data


def apply_category_filter(query, category: str | None):
    if not category or category == "全部":
        return query
    terms = CATEGORY_TYPES.get(category, (category,))
    return query.where(or_(*[Place.type.ilike(f"%{term}%") for term in terms]))


def consistency_from_feedbacks(feedbacks: list[Feedback]) -> float:
    """P2-3：信息一致性 = 各结构化字段多数派占比的平均值。

    之前 consistency = 0.45 + len(sources)*0.12 + len(feedbacks)*0.08，
    这跟 verification_count 维度重复（都是"反馈多 = 高分"），且和"一致性"无关。

    改造后：对 4 个结构化字段（can_park_now / can_overnight / price_status / toilet_available）
    各算"多数派 / 有效反馈数"占比，最后取平均：
    - 5 个反馈全说"能" → 1.0（完全一致）
    - 3 个"能" + 2 个"不能" → 0.6（多数派 3/5）
    - 全是"不确定" → 0.4（中性，不参与计算）
    - 0 个反馈 → 0.4（无信息，中性）
    """
    if not feedbacks:
        return 0.4  # 无反馈时给中性值
    from collections import Counter

    fields = ["can_park_now", "can_overnight", "price_status", "toilet_available"]
    ratios: list[float] = []
    for field in fields:
        values = [
            getattr(fb, field)
            for fb in feedbacks
            if getattr(fb, field) and getattr(fb, field) != "不确定"
        ]
        if not values:
            continue
        top = Counter(values).most_common(1)[0][1]
        ratios.append(top / len(values))
    return sum(ratios) / len(ratios) if ratios else 0.4


async def recalculate_place_score(db: AsyncSession, place: Place) -> None:
    sources = fact_sources_for_place(place)
    feedbacks = list(getattr(place, "feedbacks", []) or [])
    latest_source = max((source.source_time for source in sources if source.source_time), default=place.last_verified_at)
    source_quality = round(sum(source.reliability_score for source in sources) / len(sources)) if sources else 35
    risk_count = sum(1 for feedback in feedbacks if feedback.was_warned)
    # P2-3：consistency 改用字段投票（不再用 len(sources)+len(feedbacks) 与 verification_count 重复）
    consistency = consistency_from_feedbacks(feedbacks)
    place.credibility_score = calculate_credibility_score(
        days_since(latest_source),
        verification_count=len(feedbacks),
        source_consistency=consistency,
        risk_feedback_count=risk_count,
        source_quality_score=source_quality,
    )
    place.recommendation = recommendation_from_score(place.credibility_score)
    place.source_count = len(sources)
    if latest_source:
        place.last_verified_at = latest_source
    await db.flush()


async def _resolve_search_center(
    q: str | None,
    fallback_lat: float | None,
    fallback_lon: float | None,
) -> tuple[float | None, float | None, str | None, str | None]:
    """spec 001-fix-source-geo-filter / FR-002: 三段式决策 search_center。

    Returns: (lat, lon, detected_place_name, geocoder)
    - geocoder ∈ {"local", "amap", None}
    - 当 q 为空或所有 detect 失败，返回 fallback_lat/lon + geocoder=None（保持原行为）
    """
    if q and q.strip():
        # 延迟 import 避免 router/service 循环依赖
        from app.routers.search import _tokenize, detect_place_center

        # 第 1 段：本地 14 城市表
        detected = detect_place_center(q, _tokenize(q))
        if detected:
            lat, lon, name = detected
            return lat, lon, name, "local"

        # 第 2 段：高德 geocoding fallback
        # spec 005: 传 province hint 减少同名地歧义（如「莫干山」被识别成甘肃）
        from app.services.ai_service import _infer_province_from_text
        inferred_province = _infer_province_from_text(q, None, None, None, q)
        amap_result = await geocode_query(q, province=inferred_province)
        if amap_result:
            lat, lon, name = amap_result
            return lat, lon, name, "amap"

    # 第 3 段：用户位置 fallback（保持原行为）
    return fallback_lat, fallback_lon, None, None


@router.get("")
async def list_places(
    lat: float | None = Query(30.2741),
    lon: float | None = Query(120.1551),
    radius_km: float = Query(80, ge=1, le=500),
    category: str | None = Query("全部"),
    min_credibility: int = Query(0, ge=0, le=100),
    recommendation: str | None = Query(None),
    limit: int = Query(200, ge=1, le=500),
    offset: int = Query(0, ge=0),
    q: str | None = Query(None, description="搜索词（spec 001）：识别地理意图，决定 search_center"),
    db: AsyncSession = Depends(get_db),
):
    # spec 001 / FR-001~005: 当 q 存在时按地理意图过滤；否则保持原 lat/lon
    search_lat, search_lon, detected_place, geocoder = await _resolve_search_center(q, lat, lon)

    # P1-4：距离过滤搬到 DB 端（ST_DWithin + GIST 索引），不再先拉 5000 行再 Python 算 haversine
    use_spatial = search_lat is not None and search_lon is not None
    # spec 004-filter-fuzzy-places (Bug 1 后续清扫):
    # 过滤掉 location_confidence='low'/'pending'/NULL 的历史脏数据
    # 这些 Place 是 spec 003 之前 geocode 失败时 fallback_center 生成的"猜测坐标"，
    # 地址写的是 A 地、坐标在 B 地（典型如截图里"烟台福山区"坐标在杭州周边）
    base_filters = [
        Place.status == "active",
        Place.credibility_score >= min_credibility,
        Place.location_confidence.in_(["high", "medium"]),
    ]
    if use_spatial:
        center = cast(ST_SetSRID(ST_MakePoint(search_lon, search_lat), 4326), Geography(geometry_type="POINT", srid=4326))
        distance_expr = ST_Distance(Place.location, center).label("distance_m")
        base_filters.append(ST_DWithin(Place.location, center, radius_km * 1000))
        query = select(Place, distance_expr).options(selectinload(Place.sources))
    else:
        query = select(Place).options(selectinload(Place.sources))

    query = query.where(*base_filters)
    query = apply_category_filter(query, category)
    if recommendation:
        query = query.where(Place.recommendation == recommendation)

    # 多拉一些（limit * 3）应对应用层 is_displayable_place 过滤后的丢失，仍远小于旧 5000 量级
    fetch_limit = min(limit * 3, 600)
    if use_spatial:
        query = query.order_by(Place.credibility_score.desc(), distance_expr.asc())
    else:
        query = query.order_by(Place.credibility_score.desc(), Place.source_count.desc())
    query = query.offset(offset).limit(fetch_limit)

    result = await db.execute(query)
    rows = result.all()

    items: list[dict[str, Any]] = []
    for row in rows:
        if use_spatial:
            place, dist_m = row
            distance_km = round(dist_m / 1000.0, 2) if dist_m is not None else None
        else:
            place = row[0]
            distance_km = None
        if not is_displayable_place(place):
            continue
        items.append(place_to_dict(place, distance_km=distance_km))
        if len(items) >= limit:
            break

    return {
        "total": len(items),
        "places": items,
        "search_metadata": {
            # 保留原有字段（向后兼容）
            "lat": search_lat,
            "lon": search_lon,
            "radius_km": radius_km,
            # spec 001 新增（FR-005）
            "detected_place": detected_place,
            "search_center": {"lat": search_lat, "lon": search_lon} if geocoder else None,
            "geocoder": geocoder,
        },
    }


@router.get("/{place_id}")
async def get_place_detail(place_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    place = await db.scalar(
        select(Place)
        .where(Place.id == place_id)
        .options(selectinload(Place.sources), selectinload(Place.feedbacks))
    )
    if not place or not is_displayable_place(place):
        raise HTTPException(status_code=404, detail="Place not found")
    return place_to_dict(place, detail=True)


@router.post("/{place_id}/feedback")
async def submit_feedback(place_id: uuid.UUID, payload: FeedbackIn, db: AsyncSession = Depends(get_db)):
    place = await db.scalar(
        select(Place)
        .where(Place.id == place_id)
        .options(selectinload(Place.sources), selectinload(Place.feedbacks))
    )
    if not place or not is_displayable_place(place):
        raise HTTPException(status_code=404, detail="Place not found")
    feedback = Feedback(place_id=place.id, **payload.model_dump())
    db.add(feedback)
    await db.flush()
    place.feedbacks.append(feedback)
    await recalculate_place_score(db, place)
    await db.commit()
    await db.refresh(feedback)
    return {"feedback": feedback_to_dict(feedback), "place": place_to_dict(place)}


@router.post("/save-candidate")
async def save_candidate(payload: SaveCandidateRequest, db: AsyncSession = Depends(get_db)):
    place = Place(
        name=payload.name,
        type=payload.type,
        latitude=payload.latitude,
        longitude=payload.longitude,
        location=WKTElement(f"POINT({payload.longitude} {payload.latitude})", srid=4326),
        address=payload.address,
        city=payload.city,
        district=payload.district,
        province=payload.province,
        location_confidence=payload.location_confidence,
        geo_source=payload.geo_source,
        ai_rating=payload.ai_rating,
        credibility_score=payload.credibility_score,
        recommendation=payload.recommendation,
        source_count=len(payload.sources or []),
        price_clues=payload.price_clues,
        overnight_clues=payload.overnight_clues,
        toilet_status=payload.toilet_status,
        water_status=payload.water_status,
        electricity_status=payload.electricity_status,
        vehicle_fit=payload.vehicle_fit,
        risk_tags=payload.risk_tags,
        ai_summary=payload.ai_summary,
        positive_summary=payload.positive_summary,
        negative_summary=payload.negative_summary,
        last_verified_at=payload.last_verified_at,
        data_origin="ai_candidate",
        status="pending_review",
    )
    db.add(place)
    await db.flush()
    for raw_source in payload.sources or []:
        db.add(
            Source(
                place_id=place.id,
                source_type=raw_source.get("source_type") or "公开内容",
                source_url=raw_source.get("source_url") or raw_source.get("url"),
                domain=raw_source.get("domain"),
                title=raw_source.get("title"),
                snippet=raw_source.get("snippet"),
                reliability_score=raw_source.get("reliability_score") or 35,
            )
        )
    await db.commit()
    return {"id": str(place.id), "status": place.status}


@utility_router.post("/geocode")
async def geocode(payload: GeocodeRequest):
    result = await geocode_with_amap(payload.name, payload.address_hint, payload.city, payload.province)
    if not result:
        raise HTTPException(status_code=404, detail="无法获得可信地理编码结果")
    return result
