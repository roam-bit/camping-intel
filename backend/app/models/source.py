from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import Optional

from app.database import Base

TIMESTAMPTZ = TIMESTAMP(timezone=True)


class Source(Base):
    """信息来源表。只保存标题、摘要、链接和结构化抽取结果，不保存全文。"""

    __tablename__ = "sources"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    place_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("places.id", ondelete="CASCADE"), nullable=False
    )
    source_type: Mapped[str] = mapped_column(String(50), nullable=False, default="公开内容")
    source_url: Mapped[Optional[str]] = mapped_column(Text)
    domain: Mapped[Optional[str]] = mapped_column(String(255))
    title: Mapped[Optional[str]] = mapped_column(Text)
    snippet: Mapped[Optional[str]] = mapped_column(Text)
    source_time: Mapped[Optional[datetime]] = mapped_column(TIMESTAMPTZ)
    # spec-007: source_time 的取值途径（url_path / meta_og / citation / snippet / ...）
    # NULL = spec-007 之前的历史数据；回灌脚本据此识别要重跑
    source_time_method: Mapped[Optional[str]] = mapped_column(String(40))
    extracted_info: Mapped[Optional[dict]] = mapped_column(JSONB)
    reliability_score: Mapped[int] = mapped_column(Integer, default=35)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMPTZ, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    place: Mapped["Place"] = relationship("Place", back_populates="sources")
