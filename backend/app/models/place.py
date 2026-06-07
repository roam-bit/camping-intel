from __future__ import annotations

import uuid
from datetime import datetime, timezone

from geoalchemy2 import Geography
from sqlalchemy import ARRAY, Float, Integer, String, Text
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import Optional

from app.database import Base

TIMESTAMPTZ = TIMESTAMP(timezone=True)


class Place(Base):
    """POI 底库点位表。"""

    __tablename__ = "places"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    type: Mapped[str] = mapped_column(String(50), nullable=False, default="未知")
    latitude: Mapped[float] = mapped_column(Float, nullable=False)
    longitude: Mapped[float] = mapped_column(Float, nullable=False)
    location: Mapped[Optional[str]] = mapped_column(Geography(geometry_type="Point", srid=4326))
    address: Mapped[Optional[str]] = mapped_column(Text)
    city: Mapped[Optional[str]] = mapped_column(String(100))
    district: Mapped[Optional[str]] = mapped_column(String(100))
    province: Mapped[str] = mapped_column(String(100), nullable=False, default="浙江省")
    location_confidence: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    geo_source: Mapped[Optional[str]] = mapped_column(String(50))

    ai_rating: Mapped[Optional[float]] = mapped_column(Float)
    credibility_score: Mapped[int] = mapped_column(Integer, default=0)
    heat_level: Mapped[Optional[str]] = mapped_column(String(20))
    recommendation: Mapped[str] = mapped_column(String(20), default="caution")
    source_count: Mapped[int] = mapped_column(Integer, default=0)
    mention_count: Mapped[Optional[int]] = mapped_column(Integer)

    price_clues: Mapped[Optional[list[str]]] = mapped_column(ARRAY(String))
    overnight_clues: Mapped[Optional[list[str]]] = mapped_column(ARRAY(String))
    toilet_status: Mapped[Optional[str]] = mapped_column(String(20))
    water_status: Mapped[Optional[str]] = mapped_column(String(20))
    electricity_status: Mapped[Optional[str]] = mapped_column(String(20))
    height_limit: Mapped[Optional[str]] = mapped_column(String(50))
    vehicle_fit: Mapped[Optional[list[str]]] = mapped_column(ARRAY(String))
    risk_tags: Mapped[Optional[list[str]]] = mapped_column(ARRAY(String))

    positive_summary: Mapped[Optional[str]] = mapped_column(Text)
    negative_summary: Mapped[Optional[str]] = mapped_column(Text)
    ai_summary: Mapped[Optional[str]] = mapped_column(Text)
    source_summary: Mapped[Optional[str]] = mapped_column(Text)

    last_verified_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMPTZ)
    cached_from_query: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMPTZ, default=lambda: datetime.now(timezone.utc), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMPTZ,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )

    data_origin: Mapped[Optional[str]] = mapped_column(String(50))
    status: Mapped[str] = mapped_column(String(20), default="active")

    # spec-006 微头条话题页深抓：命中时存原话题页 URL（source_url 已被替换为单帖 permalink）
    topic_url_original: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    sources: Mapped[list["Source"]] = relationship("Source", back_populates="place", cascade="all, delete")
    feedbacks: Mapped[list["Feedback"]] = relationship("Feedback", back_populates="place", cascade="all, delete")
