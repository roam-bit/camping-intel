from __future__ import annotations

import hashlib

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.config import settings
from app.services.cache import cache_get, cache_set
from app.utils.coord_converter import gcj02_to_wgs84
from app.utils.logger import get_logger

logger = get_logger(__name__)

AMAP_GEOCODE_API_URL = "https://restapi.amap.com/v3/geocode/geo"

GEOCODE_QUERY_CACHE_TTL = 7 * 86400  # 7 天（搜索词的地理意图很稳定）
GEOCODE_QUERY_TIMEOUT = 2.0  # 比 geocode_with_amap 短（用户在等结果）


@retry(
    stop=stop_after_attempt(2),
    wait=wait_exponential(multiplier=1, min=0.5, max=2),
    retry=retry_if_exception_type((httpx.TimeoutException, httpx.HTTPError)),
    reraise=True,
)
async def _amap_geocode_get(client: httpx.AsyncClient, params: dict) -> dict:
    """单次高德 geocode HTTP 调用，P2-6 自动重试 2 次（短退避 0.5-2s）。"""
    response = await client.get(AMAP_GEOCODE_API_URL, params=params)
    return response.json()


def amap_key() -> str:
    """后端 REST geocoding 用的 key。

    优先级：amap_rest_key > amap_api_key > amap_web_key
    - amap_rest_key: 高德「Web 服务」类型 key（/v3/geocode/geo 等 REST API 专用）
    - amap_web_key:  高德「Web 端 JS」类型 key（前端地图渲染用）—— 调 REST 会返回
      USERKEY_PLAT_NOMATCH。仅作最后 fallback 以防部署忘了配 rest_key。
    """
    return (settings.amap_rest_key or settings.amap_api_key or settings.amap_web_key or "").strip()


def clean_geocode_name(value: str) -> str:
    value = " ".join(str(value or "").strip().split())
    for token in ("免费", "可过夜", "适合自驾", "自驾", "露营"):
        value = value.replace(token, "")
    for suffix in ("露营基地", "露营地", "露营点", "营地", "基地"):
        if value.endswith(suffix) and len(value) > len(suffix) + 1:
            value = value[: -len(suffix)]
    return value.strip()


def geocode_variants(name: str, address_hint: str | None, city: str | None, province: str | None) -> list[str]:
    base = clean_geocode_name(name)
    parts = [province or "浙江省", city or "", address_hint or "", base]
    variants = [
        " ".join(item for item in parts if item),
        " ".join(item for item in [province or "浙江省", city or "", base] if item),
        " ".join(item for item in [province or "浙江省", address_hint or "", base] if item),
        " ".join(item for item in [province or "浙江省", base] if item),
    ]
    if address_hint:
        variants.append(" ".join(item for item in [province or "浙江省", city or "", address_hint] if item))
    return list(dict.fromkeys(item for item in variants if len(item.strip()) >= 2))


async def geocode_with_amap(
    name: str,
    address_hint: str | None = None,
    city: str | None = None,
    province: str | None = "浙江省",
) -> dict | None:
    key = amap_key()
    if not key:
        return None
    async with httpx.AsyncClient(timeout=8) as client:
        for address in geocode_variants(name, address_hint, city, province):
            params = {"key": key, "address": address, "output": "json"}
            if city:
                params["city"] = city
            try:
                data = await _amap_geocode_get(client, params)
            except Exception as exc:
                # 重试 2 次后仍失败：fallback 到下一个 variant（保持现有"软重试 across variants"行为）
                logger.warning(
                    "amap.geocode_failed",
                    extra={"address": address[:60], "err_type": type(exc).__name__, "err": str(exc)[:120]},
                )
                continue
            if data.get("status") != "1" or not data.get("geocodes"):
                continue
            first = data["geocodes"][0]
            level = str(first.get("level") or "")
            if level in {"国家", "省", "市", "区县"}:
                continue
            location = str(first.get("location") or "")
            if "," not in location:
                continue
            lon_gcj, lat_gcj = [float(item) for item in location.split(",", 1)]
            lon_wgs, lat_wgs = gcj02_to_wgs84(lon_gcj, lat_gcj)
            return {
                "lat": round(lat_wgs, 6),
                "lon": round(lon_wgs, 6),
                "confidence": "medium" if level != "兴趣点" else "high",
                "provider": f"amap:{level or 'unknown'}",
                "matched_address": first.get("formatted_address") or address,
            }
    return None


async def geocode_query(
    q: str | None,
    *,
    city: str | None = None,
    province: str | None = None,
) -> tuple[float, float, str] | None:
    """识别用户搜索词的地理意图（spec 001 Bug 2 修复 + spec 005 加 city hint）。

    与 geocode_with_amap 不同：
    - 接受单个 query 字符串（不需要 name/city/province 结构化字段）
    - **不**过滤 level=市/区县（用户搜"漠河"就是要市级坐标）
    - Redis cache 7 天（搜索词的地理意图很稳定）
    - 比 geocode_with_amap 短超时（2s）—— 用户在等结果，不能拖

    Args:
        q: 搜索词（如 "莫干山"、"漠河"）
        city: 城市 hint（如 "湖州市"）—— spec 005，减少"莫干山被识别成甘肃同名地"歧义
        province: 省份 hint（如 "浙江省"）—— spec 005，作为最大范围限定

    Returns:
        (lat, lon, name) WGS-84 坐标 + 高德格式化后的地址名；任何异常/无结果都返回 None
    """
    if not q or not q.strip():
        return None
    key = amap_key()
    if not key:
        return None

    # cache key 包含 hint（不同 hint 视为不同查询，避免错配缓存）
    cache_parts = [q, city or "", province or ""]
    cache_key = f"geocode_query:{hashlib.md5('|'.join(cache_parts).encode('utf-8')).hexdigest()}"
    cached = await cache_get(cache_key)
    if cached:
        return (cached["lat"], cached["lon"], cached["name"])

    # 构造高德 params；province 拼到 address 前缀（高德对省份的支持是通过 address 字符串）
    # city 用独立参数（高德官方推荐）
    address = f"{province}{q}" if province else q
    params = {"key": key, "address": address, "output": "json"}
    if city:
        params["city"] = city

    try:
        async with httpx.AsyncClient(timeout=GEOCODE_QUERY_TIMEOUT) as client:
            data = await _amap_geocode_get(client, params)
    except Exception as exc:  # noqa: BLE001 —— 静默失败上层会 fallback
        logger.warning(
            "geocode_query.failed",
            extra={"q": q[:60], "err_type": type(exc).__name__, "err": str(exc)[:120]},
        )
        return None

    if data.get("status") != "1" or not data.get("geocodes"):
        return None
    first = data["geocodes"][0]
    location = str(first.get("location") or "")
    if "," not in location:
        return None
    try:
        lon_gcj, lat_gcj = [float(x) for x in location.split(",", 1)]
    except (ValueError, TypeError):
        return None
    lon_wgs, lat_wgs = gcj02_to_wgs84(lon_gcj, lat_gcj)
    name = first.get("formatted_address") or q
    payload = {"lat": round(lat_wgs, 6), "lon": round(lon_wgs, 6), "name": name}
    await cache_set(cache_key, payload, ttl_seconds=GEOCODE_QUERY_CACHE_TTL)
    return (payload["lat"], payload["lon"], payload["name"])
