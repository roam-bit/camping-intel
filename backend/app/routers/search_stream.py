"""SSE 流式搜索端点（MVP 7.5 阶段一）。

POST /api/v1/search/stream
- 复用 ai_search_pipeline_stream 的事件序列
- 用 SSE（Server-Sent Events）协议把每个事件推给前端
- 第一版不接 Ark stream=True（search 阶段仍阻塞）；目标是把"等 30-50s 大黑屏"
  拆成"5-15s 看到 answer+sources → 再等 extract"，UX 改进的核心是事件分阶段

第二轮（7.5-B/C）才接入 Ark stream=True + extract 后台化。
"""
from __future__ import annotations

import json

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.services.ai_service import ai_search_pipeline_stream
from app.services.cache import cache_get

router = APIRouter(prefix="/api/v1", tags=["search-stream"])


class StreamSearchRequest(BaseModel):
    q: str = Field(..., min_length=2)
    limit: int = Field(12, ge=1, le=50)
    radius_km: int | None = Field(80, ge=1, le=500)


def _sse_format(event_name: str, data: dict) -> str:
    """格式化为 SSE 协议帧：每帧以 \\n\\n 结尾。"""
    payload = json.dumps(data, ensure_ascii=False, default=str)
    return f"event: {event_name}\ndata: {payload}\n\n"


@router.post("/search/stream")
async def search_stream(payload: StreamSearchRequest, db: AsyncSession = Depends(get_db)):
    async def event_generator():
        try:
            async for event in ai_search_pipeline_stream(
                db,
                query=payload.q,
                limit=payload.limit,
                radius_km=payload.radius_km,
            ):
                yield _sse_format(event["event"], event["data"])
        except Exception as exc:  # noqa: BLE001 — 任何上游异常都要给前端一个 error 事件再关流
            yield _sse_format("error", {"warning": str(exc), "warning_code": "pipeline_exception"})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # 让 nginx 等反代不缓冲（生产部署时关键）
            "Connection": "keep-alive",
        },
    )


@router.get("/search/extract-result/{cache_key}")
async def get_extract_result(cache_key: str):
    """7.5-D: 前端 polling extract 后台 task 的结果。

    主 SSE 流在 search_done 后立即 yield complete (extract_pending=True, extract_cache_key=key)，
    前端拿到 key 后 2 秒一次 poll 这个 endpoint，直到 ready=True 拿到 spots/unmapped。

    Returns:
        - 后台未完成: {"ready": false}（202 表达"未就绪"）
        - 后台已完成: 完整 response dict（ready=true, spots=..., unmapped_candidates=...,
          extract_timeout 标注是否走了 timeout 降级）
    """
    if not cache_key.isalnum() or len(cache_key) > 128:
        # 防御性参数校验（cache_key 是 hex hash，应只含 [0-9a-f]）
        return {"ready": False, "error": "invalid_cache_key"}
    result = await cache_get(f"extract:result:{cache_key}")
    if result is None:
        return {"ready": False}
    return result
