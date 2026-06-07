from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app.database import engine
from app.config import settings
from app import models  # noqa: F401  # 确保所有 SQLAlchemy 模型注册到 Base.metadata
from app.utils.logger import get_logger  # P3-1：触发 root logger JsonFormatter 初始化

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：建表/索引交给 alembic（P1-2/P1-3），启动只确保 postgis 扩展存在。"""
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis"))
    yield
    await engine.dispose()


app = FastAPI(
    title="AI驻车露营情报助手",
    description="POI 底库 + AI 联网增强 + 高德地图可视化",
    version="0.3.0",
    lifespan=lifespan,
)

origins = settings.cors_allow_origins or [
    "http://localhost:10086",
    "http://127.0.0.1:10086",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


@app.get("/api/v1/health")
async def health():
    return {"status": "ok", "version": "0.3.0"}


# 注册路由
from app.routers import ai, places, qrcode_router, search, search_stream

app.include_router(places.router)
app.include_router(places.utility_router)
app.include_router(ai.router)
app.include_router(search.router)
app.include_router(search_stream.router)
app.include_router(qrcode_router.router)  # spec-017 B 方案：PNG 二维码生成（供小程序长按识别）
