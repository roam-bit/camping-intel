# Contract: meta_time_service 内部接口

**Date**: 2026-05-20

本服务**不**对外暴露 HTTP API，仅作为后端内部模块被 `ai_service.resolve_published_at` 和 `scripts/backfill_meta_time.py` 调用。

---

## 1. 主入口

```python
# backend/app/services/meta_time_service.py

async def resolve_meta_published_at(
    url: str,
    *,
    http_client: httpx.AsyncClient | None = None,  # 测试可注入
    timeout_seconds: float = 5.0,
) -> MetaTimeResult:
    """从信源 URL 的 HTML <head> meta 标签解析真实发布时间。

    Args:
        url: 信源 URL（任意域名）
        http_client: 可选依赖注入；不传则用默认 httpx.AsyncClient
        timeout_seconds: 单次 GET 超时，默认 5s

    Returns:
        MetaTimeResult（永不抛异常；所有错误映射到对应 status）

    Cache:
        - 命中 Redis 直接返回（cache_hit=True，不消耗 Semaphore）
        - 未命中 → Semaphore(5) → HTTP GET → 解析 → SETEX 24h
        - 失败也缓存（避免反复抓死站）

    Concurrency:
        进程级 asyncio.Semaphore(5)（同 spec-006 全局并发上限，但独立 sem 实例）
    """
    ...
```

---

## 2. MetaTimeResult Pydantic 模型

```python
from typing import Literal
from pydantic import BaseModel
from datetime import datetime

MetaTimeStatus = Literal["matched", "timeout", "http_error", "no_meta", "error"]
MetaSourceTag = Literal[
    "og:published_time",
    "article:published_time",
    "publishdate",
    "pubdate",
    "datePublished",
]

class MetaTimeResult(BaseModel):
    url: str
    published_at: datetime | None = None
    status: MetaTimeStatus = "no_meta"
    source_tag: MetaSourceTag | None = None
    duration_ms: int = 0
    cache_hit: bool = False
```

---

## 3. ai_service 集成点

```python
# backend/app/services/ai_service.py（resolve_published_at 改造伪代码）

async def resolve_published_at(
    url: str | None,
    citation_published_at: Any = None,
    snippet: str | None = None,
) -> tuple[datetime | None, str | None]:
    """spec-007 起返回 (datetime, method)：method 是取值途径，可写入 sources.source_time_method。

    优先级链：
    1. URL 路径日期 → method=url_path
    2. (新) HTML meta → method=meta_og / meta_article_published / ...
    3. citation.published_at → method=citation
    4. snippet 启发式 → method=snippet
    5. 全部 None → method=None
    """
    if (dt := extract_date_from_url(url)):
        return dt, "url_path"
    # spec-007: 仅当 URL 路径无日期时调 meta
    if url:
        result = await resolve_meta_published_at(url)
        if result.status == "matched":
            method = f"meta_{result.source_tag.replace(':', '_').replace('-', '_')}"
            # 规整为枚举值：og:published_time → meta_og_published_time → 我们存 meta_og
            method_map = {
                "og:published_time": "meta_og",
                "article:published_time": "meta_article_published",
                "publishdate": "meta_publishdate",
                "pubdate": "meta_pubdate",
                "datePublished": "meta_itemprop_date",
            }
            return result.published_at, method_map.get(result.source_tag, "meta_og")
    if (dt := parse_source_date(citation_published_at)):
        return dt, "citation"
    if (dt := parse_source_date(snippet)):
        return dt, "snippet"
    return None, None
```

**调用方 `sources_from_citations` 改造**：

```python
date, method = await resolve_published_at(url, citation_published_at, snippet)
source_dict = {
    ...,
    "published_at": date.date().isoformat() if date else None,
    "source_time_method": method,
}
```

**`upsert_ai_places` 改造**：写入 Source 模型时同步带上 `source_time_method`。

---

## 4. meta 标签匹配规则

```python
# 编译好的正则常量（按优先级顺序检查）
_META_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("og:published_time", re.compile(
        r'<meta\s+[^>]*property=["\']og:published_time["\'][^>]*content=["\']([^"\']+)["\']',
        re.IGNORECASE,
    )),
    ("article:published_time", re.compile(
        r'<meta\s+[^>]*property=["\']article:published_time["\'][^>]*content=["\']([^"\']+)["\']',
        re.IGNORECASE,
    )),
    ("publishdate", re.compile(
        r'<meta\s+[^>]*name=["\']publishdate["\'][^>]*content=["\']([^"\']+)["\']',
        re.IGNORECASE,
    )),
    ("pubdate", re.compile(
        r'<meta\s+[^>]*name=["\']pubdate["\'][^>]*content=["\']([^"\']+)["\']',
        re.IGNORECASE,
    )),
    ("datePublished", re.compile(
        r'<meta\s+[^>]*itemprop=["\']datePublished["\'][^>]*content=["\']([^"\']+)["\']',
        re.IGNORECASE,
    )),
]
```

**注意**：以上正则只匹配 `content` 在 `property/name/itemprop` **之后**的写法。HTML 标准允许属性顺序任意，为覆盖反向顺序需要再加 5 条镜像正则（或换成更宽松的 lookahead）。本期保守起见做正向匹配，命中率不够再扩。

---

## 5. 时间格式宽松解析

```python
def _parse_meta_time_value(raw: str) -> datetime | None:
    """支持 ISO 8601 / RFC 2822 / 中文日期。"""
    raw = raw.strip()
    # ISO 8601: "2026-03-15T15:41:00+08:00"
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        pass
    # 中文格式: "2026年3月15日"
    m = re.match(r"(\d{4})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})", raw)
    if m:
        try:
            return datetime(int(m[1]), int(m[2]), int(m[3]), tzinfo=timezone.utc)
        except ValueError:
            pass
    # 通用 YYYY-MM-DD / YYYY/MM/DD 等
    return parse_source_date(raw)  # 复用 ai_service.parse_source_date
```

---

## 6. 时间合理性校验

```python
_MIN_VALID_TIME = datetime(2010, 1, 1, tzinfo=timezone.utc)

def _is_valid_publish_time(dt: datetime) -> bool:
    now = datetime.now(timezone.utc)
    max_valid = now + timedelta(days=1)
    return _MIN_VALID_TIME <= dt <= max_valid
```

不在区间内的 → 视为解析失败（status=no_meta），继续走原 fallback 链。

---

## 7. 结构化日志格式

```json
{
  "event": "meta_time.resolved",
  "url": "https://post.smzdm.com/p/az8pvqqr/",
  "status": "matched",
  "source_tag": "article:published_time",
  "published_at": "2026-03-15T15:41:00+08:00",
  "duration_ms": 1234,
  "cache_hit": false
}
```

字段顺序固定，便于 jq / Grafana 解析。
