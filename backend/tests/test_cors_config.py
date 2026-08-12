"""spec-011 US4：锁住后端 CORS「可配置 + 安全回退」行为，防回归。

背景：微信小程序不走浏览器 CORS 校验，CORS 只影响 H5 生产站点。FR-008 要求
CORS 白名单能经配置项（CORS_ALLOW_ORIGINS）加入生产域名，且未配置时安全回退到
本地默认白名单、后端不报错。研究阶段（research.md D4）确认现有代码已满足，本文件
把该行为固化为回归测试——防止未来有人改 config.py / main.py 时悄悄改坏。
"""
from __future__ import annotations

from pathlib import Path

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


def test_cors_origins_from_env_var_comma_string(monkeypatch):
    """回归（2026-08-12）：**从环境变量/.env 读**逗号分隔写法时，后端必须能启动。

    防止这个 bug 再来——本文件上面那些用例全都是 `Settings(cors_allow_origins=...)`
    直接传参构造，走的是 init 来源；而真实运行时值来自 .env / 环境变量，走的是
    env 来源。pydantic-settings 对「纯 list 类型」的字段会先把 env 值做 JSON 解析，
    `A,B` 直接抛 JSONDecodeError，上面的 field_validator 连执行机会都没有。

    后果实测：学生 `cp .env.example .env` 之后后端启动即崩，而这 5 条测试全绿。
    教训：构造路径测过了 ≠ 真实路径测过了，两条都要锁。
    """
    monkeypatch.setenv("CORS_ALLOW_ORIGINS", "http://localhost:10086, http://127.0.0.1:10086")
    settings = Settings(_env_file=None)
    assert settings.cors_allow_origins == [
        "http://localhost:10086",
        "http://127.0.0.1:10086",
    ]


def test_env_example_cors_line_is_actually_loadable(monkeypatch):
    """回归（2026-08-12）：`.env.example` 里 CORS 那一行的写法必须真能被解析。

    学生拿到项目的第一步就是 `cp .env.example .env`。这一行写成解析不了的格式，
    等于所有人后端都起不来——所以直接拿模板文件里的真实字面量来跑一遍。
    """
    env_example = Path(__file__).resolve().parents[2] / ".env.example"
    assert env_example.exists(), "根目录 .env.example 不该消失，它是学生的第一步"

    raw = None
    for line in env_example.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line.startswith("CORS_ALLOW_ORIGINS="):
            raw = line.split("=", 1)[1]
            break
    assert raw, ".env.example 里应保留 CORS_ALLOW_ORIGINS 示例行"

    monkeypatch.setenv("CORS_ALLOW_ORIGINS", raw)
    settings = Settings(_env_file=None)
    assert isinstance(settings.cors_allow_origins, list)
    assert all(o.startswith("http") for o in settings.cors_allow_origins)


def test_main_resolves_nonempty_origins():
    """main.py 解析出的 origins 必须是非空 list ——
    无论走「配置项」还是「回退本地默认」，跨域中间件都不能拿到空白名单。
    """
    import app.main as main_module

    assert isinstance(main_module.origins, list)
    assert len(main_module.origins) >= 1
    assert all(isinstance(o, str) and o.startswith("http") for o in main_module.origins)
