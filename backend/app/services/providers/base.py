"""SearchProvider 接口定义。

POC 阶段只有 ArkSeedProvider 实现；DeepSeek / Qwen 为 stub。
MVP 阶段：补全 stub 并接入评测脚手架，对比不同模型自带搜索工具的信源生态分布。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class ProviderMetrics:
    """单次 provider 调用的可观测指标。

    评测脚手架以这些字段为基础聚合：
    - elapsed_seconds: 这一步实际耗时（不含网络等待外部因素之外的纯调用）
    - input_tokens / output_tokens: token 计量，用于成本与吞吐对比
    - model_id: 具体调用的模型版本（同一 provider 切不同模型时可区分）
    - cost_cny: 人民币成本估算（根据模型价格表和 token 数推算，未知模型为 None）
    """

    elapsed_seconds: float | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None
    model_id: str | None = None
    cost_cny: float | None = None


@dataclass
class SearchResult:
    """provider.search() 的返回值。

    answer_text: LLM 给出的自然语言回答（用户最终能在 UI 顶部看到的）
    sources: list[dict]，每条至少含 id/url/domain/title/snippet/published_at/reliability_score
    warning: 面向用户的提示文案；None 表示无警告
    warning_code: 评测/分析用的稳定分类码，如 'empty_answer' / 'no_traceable_sources'
    metrics: 这次 search 调用的可观测指标
    """

    answer_text: str
    sources: list[dict[str, Any]] = field(default_factory=list)
    warning: str | None = None
    warning_code: str | None = None
    metrics: ProviderMetrics = field(default_factory=ProviderMetrics)


@dataclass
class ExtractResult:
    """provider.extract() 的返回值。

    结构与现有 call_seed_structured 输出一致，便于 normalize_candidates 直接消费。
    """

    spots: list[dict[str, Any]] = field(default_factory=list)
    unmapped_candidates: list[dict[str, Any]] = field(default_factory=list)
    query_summary: str = ""
    metrics: ProviderMetrics = field(default_factory=ProviderMetrics)

    def to_dict(self) -> dict[str, Any]:
        return {
            "spots": self.spots,
            "unmapped_candidates": self.unmapped_candidates,
            "query_summary": self.query_summary,
        }


class SearchProvider(Protocol):
    """所有 provider 必须实现的接口。

    name: provider 标识，与 settings.search_provider 配置值对应。
    search: 联网检索，返回 LLM 答案 + 信源列表 + 指标。
    extract: 从答案和信源中抽取结构化点位 + 指标。
    """

    name: str

    async def search(self, query: str, limit: int) -> SearchResult: ...

    async def extract(
        self,
        query: str,
        answer_text: str,
        sources: list[dict[str, Any]],
        limit: int,
    ) -> ExtractResult: ...
