"""DeepSeek provider stub。

MVP 阶段补全。DeepSeek 自带的搜索工具偏全球/知识库内容，与字节系（头条/抖音）和阿里系（B站/知乎）形成互补。
"""
from __future__ import annotations

from typing import Any

from app.services.providers.base import ExtractResult, SearchResult


class DeepSeekProvider:
    name = "deepseek"

    async def search(self, query: str, limit: int) -> SearchResult:
        raise NotImplementedError(
            "DeepSeek provider 尚未实现；MVP 阶段补全。当前请使用 search_provider='ark_seed'。"
        )

    async def extract(
        self,
        query: str,
        answer_text: str,
        sources: list[dict[str, Any]],
        limit: int,
    ) -> ExtractResult:
        raise NotImplementedError(
            "DeepSeek provider 尚未实现；MVP 阶段补全。"
        )
