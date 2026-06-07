from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class SourceOut(BaseModel):
    id: str
    source_type: str
    source_url: str | None = None
    domain: str | None = None
    title: str | None = None
    snippet: str | None = None
    source_time: datetime | None = None
    reliability_score: int = 35


class FeedbackIn(BaseModel):
    can_park_now: str = "不确定"
    can_overnight: str = "不确定"
    price_status: str = "不确定"
    toilet_available: str = "不确定"
    was_warned: bool = False
    vehicle_type: str | None = None
    comment: str | None = None


class FeedbackOut(FeedbackIn):
    id: str
    created_at: datetime


class PlaceBase(BaseModel):
    name: str
    type: str = "未知"
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    address: str | None = None
    city: str | None = None
    district: str | None = None
    province: str = "浙江省"
    location_confidence: str = "pending"
    geo_source: str | None = None
    ai_rating: float | None = None
    credibility_score: int = 0
    recommendation: str = "caution"
    source_count: int = 0
    price_clues: list[str] = Field(default_factory=list)
    overnight_clues: list[str] = Field(default_factory=list)
    toilet_status: str | None = None
    water_status: str | None = None
    electricity_status: str | None = None
    vehicle_fit: list[str] = Field(default_factory=list)
    risk_tags: list[str] = Field(default_factory=list)
    ai_summary: str | None = None
    positive_summary: str | None = None
    negative_summary: str | None = None
    last_verified_at: datetime | None = None
    data_origin: str | None = None
    status: str = "active"


class PlaceOut(PlaceBase):
    id: uuid.UUID
    updated_at: datetime
    distance_km: float | None = None

    model_config = {"from_attributes": True}


class PlaceDetailOut(PlaceOut):
    sources: list[SourceOut] = Field(default_factory=list)
    feedbacks: list[FeedbackOut] = Field(default_factory=list)
    disclaimer: str = "本产品信息基于公开资料、用户反馈和 AI 整理生成，仅供出行参考。实际停车、露营、过夜需遵守当地法律法规及现场管理要求。"


class PlacesResponse(BaseModel):
    total: int
    places: list[PlaceOut]


class SaveCandidateRequest(PlaceBase):
    source_ids: list[str] = Field(default_factory=list)
    sources: list[dict] = Field(default_factory=list)


class GeocodeRequest(BaseModel):
    name: str
    city: str | None = None
    province: str = "浙江省"
    address_hint: str | None = None


class SearchRequest(BaseModel):
    """统一搜索入口的请求体。

    召回策略 B（V2 决策）：
    - 先按 q 关键词 + 地理范围查 DB（关键词匹配 name + ai_summary）
    - DB 命中 ≥ ceil(limit * 0.5) 时直接返回，不调 AI（D6-2 = B）
    - 命中不足时调 AI 联网，与 DB 结果合并去重后返回
    """

    q: str = Field(..., description="用户自然语言查询")
    lat: float = Field(30.2741, ge=-90, le=90)
    lon: float = Field(120.1551, ge=-180, le=180)
    radius_km: float = Field(80, ge=1, le=500)
    limit: int = Field(12, ge=1, le=50)
