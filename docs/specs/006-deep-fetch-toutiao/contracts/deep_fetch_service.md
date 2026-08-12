# Contract: deep_fetch_service 内部接口

**Date**: 2026-05-20

本服务**不**对外暴露 HTTP API，仅作为后端内部模块被 `ai_service` / `routers/search` 调用。

---

## 1. 主入口

```python
# backend/app/services/deep_fetch_service.py

async def fetch_and_match(
    topic_url: str,
    keyword: str,
    *,
    fetcher: PostFetcher | None = None,  # 测试可注入 FakeFetcher
    relevance_threshold: float = 0.6,
    timeout_seconds: float = 15.0,
) -> DeepFetchResult:
    """
    对一个话题页 URL 触发深抓 + 关键词筛选。

    Args:
        topic_url: 已被 is_topic_aggregator_url 判定为话题页的 URL
        keyword: 用户搜索关键词（service 内部会做 NFKC 归一化）
        fetcher: 可选，依赖注入用；不传则用默认的 ToutiaoPlaywrightFetcher
        relevance_threshold: 阈值，从 config 取默认值
        timeout_seconds: Playwright 单页渲染超时

    Returns:
        DeepFetchResult（永不抛异常；所有错误都映射到 match_status=error）

    Concurrency:
        本函数受两个 semaphore 保护：
        - 进程级全局 ≤ 3
        - per-request 调用方需自行包一层 Semaphore(2)（router 调用前传入）

    Cache:
        - 命中 Redis 直接返回（cache_hit=True）
        - 未命中跑完后 SETEX TTL 24h
    """
    ...
```

---

## 2. Fetcher Protocol

```python
# backend/app/services/fetchers/base.py

from typing import Protocol
from dataclasses import dataclass
from datetime import datetime

@dataclass
class TopicPagePost:
    title: str
    text_excerpt: str
    published_at: datetime | None
    permalink_url: str

class PostFetcher(Protocol):
    """所有 fetcher 实现需满足此契约。"""

    async def fetch(
        self,
        topic_url: str,
        *,
        timeout_seconds: float = 15.0,
    ) -> list[TopicPagePost]:
        """
        渲染并抓取页内所有候选单帖。

        Raises:
            asyncio.TimeoutError: 渲染超时
            FetcherError: 其它抓取失败（含 4xx/5xx、被反爬墙挡、解析失败）

        Returns:
            可能为空 list（页面里没有任何帖子）；不应返回缺字段的对象（缺字段的应在 fetcher 内过滤）
        """
        ...
```

---

## 3. Relevance Scorer

```python
# backend/app/services/deep_fetch_service.py（同模块）

async def pick_top_relevant(
    posts: list[TopicPagePost],
    keyword: str,
    *,
    threshold: float,
) -> tuple[TopicPagePost | None, float, str]:
    """
    L1+L2 两层筛选：

    L1: 字面匹配过滤
        candidates = [p for p in posts if keyword_normalized in (p.title + p.text_excerpt).lower()]
        if not candidates: return (None, 0.0, "no_match"), fallback_mode="none"

    L2: LLM 评分
        - 候选集 == 1: 直接返回该帖，score=1.0, fallback_mode="none"
        - 候选集 >= 2:
            - Ark LLM 评分，prompt 严格 JSON 输出 {post_id, score}
            - 校验 post_id 在候选集内
            - 若 LLM 调用失败 / 超时 / JSON 解析失败:
                返回 candidates[0], score=1.0, fallback_mode="keyword_only"
            - 若 score < threshold: 返回 (None, score, "no_match"), fallback_mode="none"
            - 否则: 返回选中帖, score, fallback_mode="none"

    Returns:
        (matched_post or None, top_score, status: "matched"|"no_match")
        + fallback_mode 通过外层闭包/上下文回传
    """
    ...
```

---

## 4. 调用方契约（router 集成点）

```python
# backend/app/routers/search.py（伪代码）

# 既有的信源后处理位置加一层钩子
async def _post_process_sources(sources: list[Source], keyword: str) -> list[Source]:
    # 用 asyncio.Semaphore(2) 包 per-request 并发
    sem = asyncio.Semaphore(2)
    async def _deep_fetch_one(src: Source) -> Source | None:
        if not is_topic_aggregator_url(src.source_url, src.title):
            return src  # 非话题页直接放行
        async with sem:
            result = await fetch_and_match(src.source_url, keyword)
        if result.match_status == "matched":
            # 替换 URL + 落 topic_url_original
            src.source_url = result.matched_post.permalink_url
            src.topic_url_original = result.source_url
            return src
        else:
            # FR-013: 整体剔除
            return None

    processed = await asyncio.gather(*[_deep_fetch_one(s) for s in sources])
    return [s for s in processed if s is not None]
```

---

## 5. 日志输出契约（FR-008）

每次 `fetch_and_match` 调用结束后，**必须**输出一行结构化 JSON 日志到 stderr：

```json
{
  "event": "deep_fetch.completed",
  "url": "https://weitoutiao.zjurl.cn/topic/...",
  "keyword": "莫干山",
  "match_status": "matched",
  "top_score": 0.82,
  "duration_ms": 8421,
  "posts_extracted": 12,
  "fallback_mode": "none",
  "cache_hit": false
}
```

字段顺序固定，便于后续 `jq` / Grafana 解析。
