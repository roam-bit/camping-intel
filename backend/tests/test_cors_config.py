"""spec-011 US4：锁住后端 CORS「可配置 + 安全回退」行为，防回归。

背景：微信小程序不走浏览器 CORS 校验，CORS 只影响 H5 生产站点。FR-008 要求
CORS 白名单能经配置项（CORS_ALLOW_ORIGINS）加入生产域名，且未配置时安全回退到
本地默认白名单、后端不报错。研究阶段（research.md D4）确认现有代码已满足，本文件
把该行为固化为回归测试——防止未来有人改 config.py / main.py 时悄悄改坏。
"""
from __future__ import annotations

from app.config import Settings


def test_cors_origins_split_from_comma_string():
    """配置项给逗号分隔字符串时，应拆成 list 并逐项 trim（生产配多个域名的写法）。"""
    settings = Settings(cors_allow_origins="https://a.example.com, https://b.example.com")
    assert settings.cors_allow_origins == [
        "https://a.example.com",
        "https://b.example.com",
    ]


def test_cors_origins_single_domain():
    """只配一个生产域名也应正确进入白名单。"""
    settings = Settings(cors_allow_origins="https://prod.example.com")
    assert settings.cors_allow_origins == ["https://prod.example.com"]


def test_cors_origins_empty_string_yields_empty_list():
    """配置项为空字符串时应得到空 list —— 这正是触发 main.py 回退本地默认的条件。"""
    settings = Settings(cors_allow_origins="")
    assert settings.cors_allow_origins == []


def test_cors_origins_blank_items_dropped():
    """逗号间的空白项应被丢弃，不产生空字符串 origin。"""
    settings = Settings(cors_allow_origins="https://a.example.com, ,  ,https://b.example.com")
    assert settings.cors_allow_origins == [
        "https://a.example.com",
        "https://b.example.com",
    ]


def test_cors_origins_list_passthrough():
    """已是 list 时原样通过，不被 validator 破坏。"""
    settings = Settings(cors_allow_origins=["https://a.example.com"])
    assert settings.cors_allow_origins == ["https://a.example.com"]


def test_main_resolves_nonempty_origins():
    """main.py 解析出的 origins 必须是非空 list ——
    无论走「配置项」还是「回退本地默认」，跨域中间件都不能拿到空白名单。
    """
    import app.main as main_module

    assert isinstance(main_module.origins, list)
    assert len(main_module.origins) >= 1
    assert all(isinstance(o, str) and o.startswith("http") for o in main_module.origins)
