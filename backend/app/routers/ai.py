from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.ai_service import ai_search_pipeline

router = APIRouter(prefix="/api/v1/ai", tags=["ai"])


class AISearchRequest(BaseModel):
    q: str = Field(..., min_length=2)
    limit: int = Field(50, ge=1, le=50)
    radius_km: int | None = Field(80, ge=1, le=500)


@router.post("/search")
async def ai_search_post(payload: AISearchRequest, db: AsyncSession = Depends(get_db)):
    try:
        return await ai_search_pipeline(db, query=payload.q, limit=payload.limit, radius_km=payload.radius_km)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/search")
async def ai_search_get(
    q: str = Query(..., min_length=2),
    limit: int = Query(50, ge=1, le=50),
    radius_km: int | None = Query(80, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
):
    try:
        return await ai_search_pipeline(db, query=q, limit=limit, radius_km=radius_km)
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
