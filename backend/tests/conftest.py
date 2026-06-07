"""测试通用 fixture（P3-2）。

设计:
- 不起独立内存数据库，直接打当前 dev Postgres（PostGIS Geography 类型 SQLite 不支持）
- 用 ASGITransport 让 httpx.AsyncClient 直接调 FastAPI app，避免起 uvicorn 子进程
"""
from __future__ import annotations

import pytest_asyncio
import httpx

# 注：必须在 import app 之前不需要做额外配置 —— .env 由 settings 自己加载
from app.main import app


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def client():
    """httpx.AsyncClient 直接打 app（ASGI 内存通信，不走真 socket）。

    session 级 fixture + session 级 loop（见 pytest.ini）—— 否则 SQLAlchemy
    async engine 跨 loop 报 "attached to a different loop"。
    """
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
