"""PostFetcher 契约定义（spec-006 contracts §2）。

所有平台 fetcher 必须实现 PostFetcher Protocol，统一返回 list[TopicPagePost]。
测试用 FakeFetcher 走同一个 Protocol，确保 pytest 与生产代码路径一致。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol


@dataclass(frozen=True)
class TopicPagePost:
    """话题页内的一条候选单帖（内存表示，不进 DB）。

    四个字段缺一不可——fetcher 实现内部应过滤掉残缺记录，不让上游 scorer 处理。
    """

    title: str
    text_excerpt: str  # 正文前 500 字截断
    published_at: datetime | None  # 解析失败为 None，不阻止入候选
    permalink_url: str


class FetcherError(Exception):
    """非 timeout 类的抓取失败（4xx/5xx / 反爬墙 / 解析失败）。

    timeout 由调用方用 asyncio.TimeoutError 单独识别。
    """


class PostFetcher(Protocol):
    """所有 fetcher 实现需满足此契约。"""

    async def fetch(
        self,
        topic_url: str,
        *,
        timeout_seconds: float = 15.0,
    ) -> list[TopicPagePost]:
        """渲染话题页并抓取所有候选单帖。

        Raises:
            asyncio.TimeoutError: 渲染超时
            FetcherError: 其它抓取失败

        Returns:
            可能为空 list（页面里没有任何帖子）；缺字段的对象**不**返回（fetcher 内自行过滤）
        """
        ...
