"""Redis 缓存模块（P1-5）。

替换 .cache/seed_web_search_cache.json 文件缓存：
- 多 worker 并发安全
- TTL 由 Redis 原生支持（ex= 参数）
- key 统一以 'cache:' 前缀，方便 redis-cli keys 'cache:*' 排障

spec-006 扩展：deep_fetch_cache_key() 为话题页深抓产 key，独立 namespace `deep_fetch:v1:`。
"""
from __future__ import annotations

import hashlib
import json
import unicodedata
from typing import Any

import redis.asyncio as redis_async

from app.config import settings


_client: redis_async.Redis | None = None


def get_redis() -> redis_async.Redis:
    global _client
    if _client is None:
        _client = redis_async.from_url(settings.redis_url, decode_responses=True)
    return _client


def _redis_key(key: str) -> str:
    # spec-006 deep_fetch: / spec-007 meta_time: 前缀独立 namespace，不再包一层 cache:
    if key.startswith(("deep_fetch:", "meta_time:")):
        return key
    return key if key.startswith("cache:") else f"cache:{key}"


async def cache_get(key: str) -> dict[str, Any] | None:
    raw = await get_redis().get(_redis_key(key))
    return json.loads(raw) if raw else None


async def cache_set(key: str, value: dict[str, Any], ttl_seconds: int) -> None:
    payload = json.dumps(value, ensure_ascii=False, default=str)
    await get_redis().set(_redis_key(key), payload, ex=ttl_seconds)


def deep_fetch_cache_key(topic_url: str, keyword: str) -> str:
    """spec-006 深抓缓存 key 生成（research.md D3）。

    - 加 v1 版本前缀：未来字段变了可整体 invalidate
    - keyword 做 NFKC + 大小写 + 去空格归一：「莫干山 」「莫干山」命中同一缓存
    - md5 后短而定长（32 字符）
    """
    keyword_normalized = unicodedata.normalize("NFKC", keyword).strip().lower()
    raw = f"{topic_url}|{keyword_normalized}"
    digest = hashlib.md5(raw.encode("utf-8")).hexdigest()
    return f"deep_fetch:v1:{digest}"


def meta_time_cache_key(url: str) -> str:
    """spec-007 信源时间 meta 解析缓存 key（research.md D3）。

    - v1 版本前缀：未来字段变了可整体 invalidate
    - md5(url)：URL 本身已规范化，无用户输入维度，不做 NFKC
    """
    digest = hashlib.md5(url.encode("utf-8")).hexdigest()
    return f"meta_time:v1:{digest}"
