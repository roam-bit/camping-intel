from typing import Union

from pydantic_settings import BaseSettings
from pydantic import field_validator


class Settings(BaseSettings):
    database_url: str = "postgresql+asyncpg://camping:camping123@localhost:5432/camping"
    redis_url: str = "redis://localhost:6379/0"
    debug: bool = False
    # 声明成 Union 而不是纯 list[str] 是必须的，不是随手写的：
    # pydantic-settings 见到「纯 list 类型」的字段，会先拿环境变量的值去做 JSON 解析，
    # 于是 .env 里人类可读的 `A,B` 直接抛 JSONDecodeError —— 下面那个 validator
    # 连执行的机会都没有。加上 str 分支后它不再走 JSON 解码，原始字符串才能交给 validator。
    # 运行时经 validator 归一化后永远是 list[str]。
    cors_allow_origins: Union[str, list[str]] = []

    @field_validator("cors_allow_origins", mode="before")
    @classmethod
    def _split_cors_origins(cls, v):
        if isinstance(v, str):
            return [item.strip() for item in v.split(",") if item.strip()]
        return v
    # 当前激活的 SearchProvider 名称（ark_seed / deepseek / qwen）；后两者目前为 stub
    search_provider: str = "ark_seed"
    ark_api_key: str = ""
    ark_model: str = "doubao-seed-2-0-mini-260428"
    ark_api_url: str = "https://ark.cn-beijing.volces.com/api/v3/responses"
    # POC 时间预算：联网检索 50s + 结构化抽取 40s = 整体 ≤90s
    # Ark 自带 web_search 对偏门 query（如"云南香格里拉露营"）经常 35-45s 才返回结果，
    # 35s 触发 timeout 的概率太高。50s 是「等得不爽但 query 大概率能完成」的平衡点。
    # 同时 max_output_tokens 已从 12000/16000 降到 4000/6000，生成阶段提速一倍。
    live_search_timeout_seconds: float = 50.0
    # 7.5-D 后 extract 在后台跑，前端 polling 不阻塞用户感知 → 之前 40s 限制可放宽
    # 实测「太湖露营」「云南香格里拉露营」这类偏门 query 经常 50-90s extract 完成
    # 120s 让 95%+ query 能拿到 spots；polling key TTL 600s 配套 ≥ 这个值
    structured_extraction_timeout_seconds: float = 120.0
    deepseek_api_key: str = ""
    deepseek_model: str = "deepseek-v4-flash"
    amap_web_key: str = ""

    # Freshness scoring defaults
    freshness_recency_weight: float = 0.40
    freshness_confirmation_weight: float = 0.25
    freshness_seasonal_weight: float = 0.15
    freshness_reliability_weight: float = 0.10
    freshness_activity_weight: float = 0.10
    freshness_half_life_days: int = 200

    # Baidu/Amap API keys (to be configured later)
    baidu_map_api_key: str = ""
    amap_api_key: str = ""
    # 高德 REST 服务 key（后端 geocoding 专用，与 amap_web_key 区分；
    # 前端 JS API 用 web_key，后端 /v3/geocode 用 rest_key —— 两者平台不同）
    amap_rest_key: str = ""

    # spec-006 微头条话题页深抓 (Phase 1)
    # 相关性阈值：候选单帖的 LLM 评分必须 ≥ 此值才视为命中，低于 = no_match
    # 0.6 来自直觉初始值，上线后据 SC-001 抽查结果回调
    deep_fetch_relevance_threshold: float = 0.6
    # Playwright 单页渲染超时；超过即降级（不抛错）
    deep_fetch_timeout_seconds: float = 15.0
    # 进程级全局并发深抓数（asyncio.Semaphore），避免多用户同时搜索时 Chromium 实例爆炸
    deep_fetch_global_concurrency: int = 3

    # spec-007 信源时间 HTML meta fallback
    # 单次 HTTP GET 超时（秒）；超过即降级 status=timeout，不抛错
    meta_time_http_timeout: float = 5.0
    # 进程级 HTTP 并发上限（asyncio.Semaphore）；含搜索路径 + 回灌脚本
    meta_time_http_concurrency: int = 5
    # HTML 体积读取上限（字节）；meta 标签都在 <head>，256KB 是 5x 余量
    meta_time_html_max_bytes: int = 262144

    model_config = {"env_file": ("../.env", ".env"), "env_file_encoding": "utf-8", "extra": "ignore"}


settings = Settings()
