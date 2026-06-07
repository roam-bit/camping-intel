"""spec-017 B 方案：生成 PNG 二维码（供微信小程序长按识别）。

为什么后端做 + 为什么走 base64 JSON：
- 微信小程序 `<Image>` 长按识别二维码只对 PNG/JPG 生效（base64 SVG 不识别）
- 小程序对网络图的 src 走 **downloadFile 域名白名单**——勾「不校验合法域名」对 image 不一定生效
- 改用 wx.request（走另一份 request 白名单、已通过）拉 base64 JSON、再喂 `<Image>` 渲染绕开 downloadFile 限制

提供两个接口：
- GET /api/v1/qrcode        → image/png 直接 stream（H5 端 / 浏览器用）
- GET /api/v1/qrcode/base64 → JSON {"data_url": "data:image/png;base64,..."}（小程序用）
"""
from __future__ import annotations

import base64
import io

import qrcode
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response


router = APIRouter(prefix="/api/v1", tags=["qrcode"])


def _generate_qr_png_bytes(url: str, size: int) -> bytes:
    """共享：根据 url 生成 PNG 字节流。"""
    qr = qrcode.QRCode(
        version=None,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10,
        border=2,
    )
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    img = img.resize((size, size))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


@router.get("/qrcode")
async def generate_qrcode(
    url: str = Query(..., min_length=1, max_length=2048, description="要编码进二维码的目标 URL"),
    size: int = Query(240, ge=80, le=600, description="二维码图片边长（px）"),
) -> Response:
    """直接返回 image/png stream（适合 H5 / 浏览器、不适合小程序）。"""
    if not url.strip():
        raise HTTPException(status_code=400, detail="url is empty")
    png_bytes = _generate_qr_png_bytes(url, size)
    return Response(
        content=png_bytes,
        media_type="image/png",
        headers={"Cache-Control": "public, max-age=604800"},
    )


@router.get("/qrcode/base64")
async def generate_qrcode_base64(
    url: str = Query(..., min_length=1, max_length=2048),
    size: int = Query(240, ge=80, le=600),
) -> dict:
    """返回 base64 PNG dataURL（适合小程序，绕开 downloadFile 域名白名单）。

    小程序前端用 wx.request（走 request 白名单、已通过）拉这个接口、
    拿 data_url 喂给 `<Image>`、长按能识别二维码（PNG 格式 + 本地数据满足微信识别条件）。
    """
    if not url.strip():
        raise HTTPException(status_code=400, detail="url is empty")
    png_bytes = _generate_qr_png_bytes(url, size)
    b64 = base64.b64encode(png_bytes).decode("ascii")
    return {"data_url": f"data:image/png;base64,{b64}"}
