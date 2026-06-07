"""Ark Seed 2.0 provider 实现。

调用字节豆包 Ark Responses API，自带 web_search 工具（信源生态偏头条/抖音系）。
当前 POC 主链路使用这个 provider。

实现策略：delegate to existing call_seed_web_answer / call_seed_structured in ai_service.py。
这样保持行为完全一致，避免重构 helper 链。MVP 阶段如需深度定制，再把代码搬过来。
"""
from __future__ import annotations

from typing import Any

from app.services.providers.base import ExtractResult, ProviderMetrics, SearchResult


# 豆包 / Ark 模型的 token 单价（元 / 1k tokens）。
# 数据来源：火山引擎价格页，2026-05 时点。MVP 阶段切换模型/接入更多 provider 时需要更新。
# 未在表中的模型会让 cost_cny 落为 None，不影响主链路，仅评测脚手架统计缺数据。
_MODEL_PRICING_CNY_PER_1K_TOKENS: dict[str, dict[str, float]] = {
    "doubao-seed-2-0-mini-260428": {"input": 0.0008, "output": 0.002},
    # 留位：MVP 接入更大模型时在此追加
    # "doubao-seed-1-6-thinking": {"input": 0.003, "output": 0.006},
}


def _calc_cost_cny(model_id: str | None, input_tokens: int | None, output_tokens: int | None) -> float | None:
    """根据模型价格表 + token 数估算这次调用的人民币成本。"""
    if not model_id:
        return None
    rates = _MODEL_PRICING_CNY_PER_1K_TOKENS.get(model_id)
    if not rates or input_tokens is None or output_tokens is None:
        return None
    cost = input_tokens / 1000 * rates["input"] + output_tokens / 1000 * rates["output"]
    return round(cost, 6)


def _build_metrics(meta: dict[str, Any], model_id: str) -> ProviderMetrics:
    """把 ai_service 返回的 meta dict 包装成 ProviderMetrics 实例，并计算 cost_cny。"""
    return ProviderMetrics(
        elapsed_seconds=meta.get("elapsed_seconds"),
        input_tokens=meta.get("input_tokens"),
        output_tokens=meta.get("output_tokens"),
        model_id=model_id,
        cost_cny=_calc_cost_cny(model_id, meta.get("input_tokens"), meta.get("output_tokens")),
    )


class ArkSeedProvider:
    name = "ark_seed"

    async def search(self, query: str, limit: int) -> SearchResult:
        # 延迟导入避免 ai_service ↔ providers 循环
        from app.config import settings
        from app.services.ai_service import call_seed_web_answer

        answer_text, sources, warning_text, warning_code, meta = await call_seed_web_answer(query, limit)
        return SearchResult(
            answer_text=answer_text,
            sources=sources,
            warning=warning_text,
            warning_code=warning_code,
            metrics=_build_metrics(meta, settings.ark_model),
        )

    async def extract(
        self,
        query: str,
        answer_text: str,
        sources: list[dict[str, Any]],
        limit: int,
    ) -> ExtractResult:
        from app.config import settings
        from app.services.ai_service import call_seed_structured

        raw, meta = await call_seed_structured(query, answer_text, sources, limit)
        return ExtractResult(
            spots=raw.get("spots") or [],
            unmapped_candidates=raw.get("unmapped_candidates") or [],
            query_summary=raw.get("query_summary") or "",
            metrics=_build_metrics(meta, settings.ark_model),
        )
