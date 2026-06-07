"""Provider 注册表，按配置名查找实例。"""
from __future__ import annotations

from app.services.providers.ark_seed import ArkSeedProvider
from app.services.providers.base import SearchProvider
from app.services.providers.deepseek import DeepSeekProvider
from app.services.providers.qwen import QwenProvider

_REGISTRY: dict[str, SearchProvider] = {
    "ark_seed": ArkSeedProvider(),
    "deepseek": DeepSeekProvider(),
    "qwen": QwenProvider(),
}


def get_provider(name: str) -> SearchProvider:
    """按名查 provider；未注册的 name 会抛 ValueError。"""
    if name not in _REGISTRY:
        raise ValueError(
            f"未知的 search_provider：{name}。可选：{list(_REGISTRY.keys())}"
        )
    return _REGISTRY[name]


def available_providers() -> list[str]:
    """列出所有已注册的 provider 名字（评测脚手架会用到）。"""
    return list(_REGISTRY.keys())
