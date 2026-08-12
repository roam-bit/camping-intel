"""H5 UI 端到端回归测试的共享 fixture。

前置条件（两个服务都要在跑，否则整个目录 skip 并给出启动提示）：
  - H5 dev server: http://localhost:10086（cd frontend && npm run dev:h5）
  - 后端 API:      http://127.0.0.1:8000（backend/.venv/bin/python -m uvicorn app.main:app）

跑法（仓库根目录）：
  backend/.venv/bin/python -m pytest frontend/e2e -q

注意：这个目录不在 backend/pytest.ini 的收集范围里——日常 `pytest backend/tests`
不会带上它（e2e 需要起服务，不适合混进纯单测）。
"""
from __future__ import annotations

import os
import socket
from urllib.parse import urlparse

import pytest
from playwright.sync_api import sync_playwright

H5_BASE = os.environ.get("H5_BASE", "http://localhost:10086")
API_BASE = os.environ.get("API_BASE", "http://127.0.0.1:8000")

DESKTOP = {"width": 1440, "height": 900}
MOBILE = {"width": 390, "height": 844}


def _port_open(url: str) -> bool:
    parsed = urlparse(url)
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    try:
        with socket.create_connection((parsed.hostname, port), timeout=2):
            return True
    except OSError:
        return False


def pytest_collection_modifyitems(config, items):
    missing = []
    if not _port_open(H5_BASE):
        missing.append(f"H5 dev server 未启动（{H5_BASE}）→ cd frontend && npm run dev:h5")
    if not _port_open(API_BASE):
        missing.append(f"后端 API 未启动（{API_BASE}）→ backend/.venv/bin/python -m uvicorn app.main:app")
    if missing:
        marker = pytest.mark.skip(reason="; ".join(missing))
        for item in items:
            item.add_marker(marker)


@pytest.fixture(scope="session")
def browser():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        yield browser
        browser.close()


def _new_page(browser, viewport):
    ctx = browser.new_context(
        viewport=viewport,
        locale="zh-CN",
        # 固定一个杭州坐标，避免 geolocation 弹窗/失败 toast 干扰断言
        geolocation={"latitude": 30.2741, "longitude": 120.1551},
        permissions=["geolocation"],
    )
    page = ctx.new_page()
    page.goto(H5_BASE)
    return page


@pytest.fixture()
def desktop_page(browser):
    page = _new_page(browser, DESKTOP)
    yield page
    page.context.close()


@pytest.fixture()
def mobile_page(browser):
    page = _new_page(browser, MOBILE)
    yield page
    page.context.close()
