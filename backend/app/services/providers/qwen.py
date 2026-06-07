"""通义千问 provider stub。

MVP 阶段补全。千问搭配的搜索工具（夸克/阿里系）偏 B站/知乎/马蜂窝，
对自驾露营场景的实测内容覆盖往往优于字节系。
"""
from __future__ import annotations

from typing import Any

from app.services.providers.base import ExtractResult, SearchResult


class QwenProvider:
    name = "qwen"

    async def search(self, query: str, limit: int) -> SearchResult:
        raise NotImplementedError(
            "Qwen provider 尚未实现；MVP 阶段补全。当前请使用 search_provider='ark_seed'。"
        )

    async def extract(
        self,
        query: str,
        answer_text: str,
        sources: list[dict[str, Any]],
        limit: int,
    ) -> ExtractResult:
        raise NotImplementedError(
            "Qwen provider 尚未实现；MVP 阶段补全。"
        )
