from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, ForeignKey, String, Text
from sqlalchemy.dialects.postgresql import TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from typing import Optional

from app.database import Base

TIMESTAMPTZ = TIMESTAMP(timezone=True)


class Feedback(Base):
    """10 秒结构化反馈。"""

    __tablename__ = "feedbacks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    place_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("places.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[Optional[str]] = mapped_column(String(100))
    can_park_now: Mapped[str] = mapped_column(String(20), default="不确定")
    can_overnight: Mapped[str] = mapped_column(String(20), default="不确定")
    price_status: Mapped[str] = mapped_column(String(20), default="不确定")
    toilet_available: Mapped[str] = mapped_column(String(20), default="不确定")
    was_warned: Mapped[bool] = mapped_column(Boolean, default=False)
    vehicle_type: Mapped[Optional[str]] = mapped_column(String(50))
    comment: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMPTZ, default=lambda: datetime.now(timezone.utc), nullable=False
    )

    place: Mapped["Place"] = relationship("Place", back_populates="feedbacks")
