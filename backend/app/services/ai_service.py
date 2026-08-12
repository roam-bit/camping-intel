from __future__ import annotations

import asyncio
import hashlib
import json
import math
import re
import time
import urllib.parse
from datetime import datetime, timezone
from typing import Any

import httpx
from geoalchemy2 import WKTElement
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.config import settings
from app.models.place import Place
from app.models.source import Source
from app.services.amap_service import geocode_with_amap
from app.services.cache import cache_get, cache_set
from app.utils.logger import get_logger

logger = get_logger(__name__)

CACHE_TTL_SECONDS = 6 * 60 * 60
LIVE_SEARCH_TIMEOUT_SECONDS = settings.live_search_timeout_seconds
STRUCTURED_EXTRACTION_TIMEOUT_SECONDS = settings.structured_extraction_timeout_seconds
MAP_REFERENCE_DOMAINS = ("openstreetmap.org", "amap.com", "map.baidu.com", "maps.google.com")

GENERIC_TERMS = ("攻略", "合集", "推荐", "哪里", "哪些", "地方", "地点", "车程", "周边露营", "露营野炊")
BAD_TERMS = ("搜索", "地图", "政策", "办法", "规定", "下载", "我们", "喜欢", "应该")
ZHEJIANG_COORDS = {
    "良渚": (30.3790, 120.0415),
    "瓶窑": (30.3857, 119.9562),
    "径山": (30.3981, 119.7917),
    "青山村": (30.4758, 119.7895),
    "刘家畈": (30.3637, 119.9491),
    "麻车头": (30.3225, 119.9480),
    "下陡门": (30.3010, 119.9340),
    "枫岭茶谷": (30.4300, 119.7670),
    "安顶山": (29.9860, 119.7790),
    "九仰坪": (30.0150, 119.7200),
    "湘溪村": (30.0670, 119.7870),
    "富春江": (30.0484, 119.9506),
    "壶源溪": (29.9290, 119.7600),
    "寺坞岭": (29.9640, 120.2170),
    "湘湖": (30.1640, 120.2300),
    "萧山": (30.1849, 120.2646),
    "萧山区": (30.1849, 120.2646),
    "余杭": (30.2739, 119.9787),
    "余杭区": (30.2739, 119.9787),
    "临平": (30.4186, 120.2996),
    "富阳": (30.0499, 119.9601),
    "富阳区": (30.0499, 119.9601),
    "临安": (30.2338, 119.7248),
    "临安区": (30.2338, 119.7248),
    "桐庐": (29.7932, 119.6915),
    "桐庐县": (29.7932, 119.6915),
    "淳安": (29.6088, 119.0431),
    "淳安县": (29.6088, 119.0431),
    "千岛湖": (29.6088, 119.0431),
    "杭州": (30.2741, 120.1551),
    "杭州市": (30.2741, 120.1551),
    "宁波": (29.8683, 121.5440),
    "宁波市": (29.8683, 121.5440),
    "温州": (27.9938, 120.6994),
    "湖州": (30.8943, 120.0868),
    "嘉兴": (30.7460, 120.7555),
    "绍兴": (30.0303, 120.5802),
    "金华": (29.0791, 119.6474),
    "衢州": (28.9701, 118.8593),
    "舟山": (29.9853, 122.2072),
    "台州": (28.6564, 121.4208),
    "丽水": (28.4676, 119.9229),
    "安吉": (30.6380, 119.6804),
    # 杭州周边热门旅游目的地（2026-06-12 补）：莫干山不在字典时走 amap 兜底，
    # 而 amap 对「莫干山」返回的是福建泉州安溪县的同名小地名 → 搜索中心跑偏 500km+、
    # DB 0 命中、AI 白等 30s+。首页示例芯片「莫干山附近营地」一点就翻车，故入典。
    "莫干山": (30.5850, 119.8770),
    "莫干山镇": (30.5850, 119.8770),
    "德清": (30.5424, 119.9776),
    "德清县": (30.5424, 119.9776),
    "浙江": (30.2656, 120.1536),
    "浙江省": (30.2656, 120.1536),
    # 主要外省/直辖市（演示阶段覆盖国内核心城市；后续应迁出 ZHEJIANG_COORDS 命名）
    "上海": (31.2304, 121.4737),
    "上海市": (31.2304, 121.4737),
    "北京": (39.9042, 116.4074),
    "北京市": (39.9042, 116.4074),
    "成都": (30.5728, 104.0668),
    "成都市": (30.5728, 104.0668),
    "深圳": (22.5431, 114.0579),
    "深圳市": (22.5431, 114.0579),
    "广州": (23.1291, 113.2644),
    "广州市": (23.1291, 113.2644),
    "重庆": (29.5630, 106.5516),
    "重庆市": (29.5630, 106.5516),
    "南京": (32.0603, 118.7969),
    "南京市": (32.0603, 118.7969),
    "苏州": (31.2989, 120.5853),
    "苏州市": (31.2989, 120.5853),
    "武汉": (30.5928, 114.3055),
    "武汉市": (30.5928, 114.3055),
    "西安": (34.3416, 108.9398),
    "西安市": (34.3416, 108.9398),
    "厦门": (24.4798, 118.0894),
    "厦门市": (24.4798, 118.0894),
    "青岛": (36.0671, 120.3826),
    "青岛市": (36.0671, 120.3826),
    "长沙": (28.2282, 112.9388),
    "长沙市": (28.2282, 112.9388),
}


def clean_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip())


def domain_of(url: str) -> str:
    try:
        return urllib.parse.urlparse(url).netloc.replace("www.", "")
    except Exception:
        return ""


def is_map_reference_url(url: str | None) -> bool:
    domain = domain_of(url or "").lower()
    return any(domain == item or domain.endswith(f".{item}") for item in MAP_REFERENCE_DOMAINS)


def scrub_internal_source_text(value: Any) -> str:
    text = clean_text(value)
    if not text:
        return ""
    text = text.replace("OSM 冷启动 POI。扩展 POI 默认低可信，不能直接视为可露营/可过夜。", "地图导入线索，需查看公开来源。")
    text = text.replace("OSM冷启动点位，需AI或用户核验", "地图导入线索，需查看公开来源。")
    text = text.replace("人工冷启动种子点，仅作 demo 演示，不能视为可露营/可过夜结论。", "人工导入线索，需查看公开来源。")
    text = text.replace("人工种子点，需 AI 或用户核验", "人工导入线索，需查看公开来源。")
    text = re.sub(r"OpenStreetMap[:：]?", "", text, flags=re.I)
    text = re.sub(r"\bOSM\b\s*", "", text)
    text = text.replace("冷启动", "导入")
    text = text.replace("来源待核验", "")
    text = text.replace("待核验", "")
    return clean_text(text)


def public_fact_source_dict(source: dict[str, Any], *, allow_topic_pages: bool = False) -> bool:
    """spec-006 起新增 allow_topic_pages 参数：

    - POC 默认 False：调用方（如下游 source_by_id 过滤）拒绝任何话题页
    - 上游 sources_from_citations 传 True：让话题页通过初筛，由 _apply_deep_fetch_to_sources 接手做深抓 →
      命中替换成单帖 URL → 单帖 URL 不再是话题页 → 下游 False 默认值再次校验不会误伤
    """
    url = source.get("url") or source.get("source_url")
    if not url or is_search_entry_url(str(url)) or is_map_reference_url(str(url)):
        return False
    if not allow_topic_pages and is_topic_aggregator_url(str(url), source.get("title")):
        return False
    if source.get("source_type") in {"地图数据", "人工冷启动"}:
        return False
    domain = str(source.get("domain") or "").lower()
    text = f"{source.get('source_type') or ''} {source.get('title') or ''} {source.get('snippet') or ''} {domain}"
    return not re.search(r"\bOSM\b|OpenStreetMap|冷启动|人工种子|种子点|seed\\.local|demo", text, flags=re.I)


def public_fact_source_model(source: Source) -> bool:
    if not source.source_url or is_search_entry_url(source.source_url) or is_map_reference_url(source.source_url):
        return False
    if is_topic_aggregator_url(source.source_url, source.title):
        return False
    if source.source_type in {"地图数据", "人工冷启动"}:
        return False
    domain = (source.domain or "").lower()
    text = f"{source.source_type or ''} {source.title or ''} {source.snippet or ''} {domain}"
    return not re.search(r"\bOSM\b|OpenStreetMap|冷启动|人工种子|种子点|seed\\.local|demo", text, flags=re.I)


def scrub_risk_tags(tags: list[str] | None, has_fact_sources: bool) -> list[str]:
    cleaned = [scrub_internal_source_text(tag) for tag in tags or []]
    cleaned = [tag for tag in cleaned if tag and not re.search(r"\bOSM\b|OpenStreetMap|冷启动|可信|信息不足", tag, flags=re.I)]
    if not has_fact_sources:
        cleaned.append("缺少公开网页信源")
    return list(dict.fromkeys(cleaned))


def public_geo_source(value: str | None) -> str | None:
    if not value:
        return value
    return "map_import" if value.lower().startswith("osm") else value


def is_search_entry_url(url: str) -> bool:
    parsed = urllib.parse.urlparse(url or "")
    domain = parsed.netloc.replace("www.", "").lower()
    path = parsed.path.lower()
    query = parsed.query.lower()
    if any(item in domain for item in ("bing.com", "google.com", "amap.com")):
        return True
    if "baidu.com" in domain and (path.startswith("/s") or "wd=" in query or "word=" in query):
        return True
    return False


# 话题/超话/hashtag 聚合页：聚合多条不相关帖子，用户点开看不到具体地点信息
# 注意：保守过滤，只挡最明显的——
# - 标题是纯 hashtag 形式（首尾都是 # 或 ＃ 或 【】）
# - 域名是已知的话题专用子域名（如微头条 weitoutiao.zjurl.cn）
# 一般 UGC 平台域名（小红书、B站、马蜂窝、豆瓣等）不挡，那些更可能是单帖。
# MVP 阶段会做信源深度抓取，从话题页提取出具体相关帖子；POC 阶段先简单过滤。
#
# 历史误判修复（2026-05）：
#   之前用 `/topic/` `/album/` `/superchat/` 路径段做通用匹配，会误判：
#     - douban.com/group/topic/N/ → 实际是小组讨论单帖
#     - 其它 /topic/ 结尾 ID 的多平台单帖
#   现已**取消通用路径匹配**，仅保留「专用子域名 + 纯 hashtag 标题」两条强信号。
_TOPIC_AGGREGATOR_DOMAINS = {
    "weitoutiao.zjurl.cn",  # 字节跳动微头条话题专用域名
}


def is_topic_aggregator_url(url: str | None, title: str | None = None) -> bool:
    """判定 URL 是否为话题聚合页（命中即被 spec-006 深抓接管 / 或被 POC 兜底过滤）。

    强信号（任意命中 → True）：
    1. 域名在 _TOPIC_AGGREGATOR_DOMAINS 白名单（如 weitoutiao.zjurl.cn）
    2. 标题是纯 hashtag 形式（如 `#免费露营地#`、`＃自驾露营＃`、`【话题】`）

    不再使用「路径含 /topic/」做通用兜底——这条规则误伤 douban /group/topic/N/
    等单帖 URL；要扩展更多平台请加进 _TOPIC_AGGREGATOR_DOMAINS 或 spec-006 Phase 2 的
    fetcher protocol。
    """
    if not url:
        return False
    parsed = urllib.parse.urlparse(url)
    domain = parsed.netloc.replace("www.", "").lower()
    if domain in _TOPIC_AGGREGATOR_DOMAINS:
        return True
    # 标题是纯 hashtag 形式（如 "#免费露营地#" / "＃自驾露营＃" / "【话题】"）
    title_clean = clean_text(title)
    if title_clean and re.match(r"^[#＃【].{1,30}[#＃】]$", title_clean):
        return True
    return False


async def _apply_deep_fetch_to_sources(
    sources: list[dict[str, Any]],
    query: str,
) -> list[dict[str, Any]]:
    """spec-006: 对识别为话题页的 sources 触发深抓 → 替换 URL 或剔除。

    - 命中：source 字典在原列表中保留，url 替换为单帖 permalink，
      stamp `_topic_url_original` 内部字段，下游 normalize_candidates 用于落 places 表
    - 未命中/超时/error：从列表中**整体剔除**（FR-013），与 location_confidence=low 过滤层对齐
    - 非话题页 source：原样透传，不触发深抓

    per-request 并发 ≤ 2（asyncio.Semaphore），与 deep_fetch_service 进程级 Semaphore(3)
    构成两层防护（FR-009）。
    """
    if not sources:
        return sources
    # 延迟导入避免循环：deep_fetch_service 依赖部分 ai_service 工具
    from app.services.deep_fetch_service import fetch_and_match

    request_sem = asyncio.Semaphore(2)

    async def _process_one(src: dict[str, Any]) -> dict[str, Any] | None:
        url = src.get("url") or src.get("source_url")
        if not url:
            return src
        if not is_topic_aggregator_url(str(url), src.get("title")):
            return src
        async with request_sem:
            result = await fetch_and_match(str(url), query)
        if result.match_status == "matched" and result.matched_post:
            new_src = dict(src)
            new_src["url"] = result.matched_post.permalink_url
            new_src["_topic_url_original"] = url  # 内部 marker，会在 normalize_candidates 阶段透传到 spot
            if result.matched_post.title:
                new_src["title"] = result.matched_post.title
            if result.matched_post.text_excerpt:
                new_src["snippet"] = result.matched_post.text_excerpt[:200]
            return new_src
        # FR-013: 失败的话题页 source 整体剔除
        return None

    processed = await asyncio.gather(*[_process_one(s) for s in sources])
    return [s for s in processed if s is not None]


def source_reliability(url: str, snippet: str = "") -> int:
    domain = domain_of(url).lower()
    text = f"{domain} {snippet}"
    if is_search_entry_url(url):
        return 25
    if domain.endswith("gov.cn"):
        return 90
    if any(item in text for item in ("实测", "亲测", "刚去", "2026", "2025")):
        return 70
    if any(item in domain for item in ("ctrip", "mafengwo", "qyer", "zhihu", "bilibili")):
        return 60
    return 45


# spec 005-precise-geocoding: 判断地址精度
# True：含街道/路/号/村/镇/景区/区/营地 等精度关键词
# False：只到城市/省级 / 空 / unknown / 大区
_CITY_LEVEL_ONLY = {
    "中国", "华东地区", "华南地区", "华北地区", "华中地区", "西南地区", "西北地区", "东北地区",
    "市中心", "市区", "市区某处", "市内", "市内某地",
    "unknown", "Unknown", "UNKNOWN", "未知", "未提到", "来源未提到",
    # 14 个直辖市/主要城市（含和不含"市"后缀双写）
    "上海", "上海市", "北京", "北京市", "成都", "成都市", "深圳", "深圳市",
    "广州", "广州市", "重庆", "重庆市", "南京", "南京市", "苏州", "苏州市",
    "武汉", "武汉市", "西安", "西安市", "厦门", "厦门市", "青岛", "青岛市",
    "长沙", "长沙市", "杭州", "杭州市", "宁波", "宁波市", "温州", "温州市",
    "湖州", "嘉兴", "绍兴", "金华", "衢州", "舟山", "台州", "丽水",
    # 省份
    "浙江", "浙江省", "江苏", "江苏省", "山东", "山东省", "广东", "广东省",
    "福建", "福建省", "四川", "四川省", "湖北", "湖北省", "湖南", "湖南省",
    "河北", "河北省", "河南", "河南省", "陕西", "陕西省", "甘肃", "甘肃省",
}

# 精度关键词（含任一即判定精确）
_PRECISION_TOKENS = (
    "路", "号", "村", "镇", "街道", "景区", "营地", "公园", "水库",
    "湖畔", "江畔", "河畔", "山顶", "山脚", "林场", "古镇", "胡同", "弄",
)


def _is_precise_address(text: str | None) -> bool:
    """spec 005: 判断 address_hint 是否精确（街道/门牌/具体场所级）。

    - True：含街道/路/号/村/镇/景区/营地 等精度关键词；或精确"X 区"（不是"市区"/"地区"）
    - False：空 / None / "unknown" / 只到城市/省份 / 大区描述

    PM 视角：这个函数是 spec 003 修复（geocode 失败不出 marker）的**上游过滤**——
    从源头让模糊地址进 unmapped 而非 geocode 流程，从根本减少错位 marker 的产生。
    """
    if not text or not isinstance(text, str):
        return False
    cleaned = text.strip()
    if not cleaned or len(cleaned) < 2:
        return False
    if cleaned in _CITY_LEVEL_ONLY:
        return False
    # 检查精度关键词
    for token in _PRECISION_TOKENS:
        if token in cleaned:
            return True
    # "X 区" 判定：含"区"且不是"市区"/"地区"也算精确
    if "区" in cleaned and "市区" not in cleaned and "地区" not in cleaned:
        return True
    return False


def parse_source_date(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value)
    match = re.search(r"(20\d{2})[-/.年](\d{1,2})(?:[-/.月](\d{1,2}))?", text)
    if not match:
        return None
    y = int(match.group(1))
    m = int(match.group(2))
    d = int(match.group(3) or 1)
    try:
        return datetime(y, m, d, tzinfo=timezone.utc)
    except ValueError:
        return None


# spec 002-fix-source-date: URL 路径里的发布日期是最稳的真理（CMS 写死，不会改）
# 覆盖常见新闻站 URL 模式：
#   /n/2024/1108/        人民网
#   /a/20260512Axxx      腾讯新闻
#   /2024/11/08/         搜狐 / 新浪部分频道
#   /news/2024-11-08/    ISO-like 横杠格式
_URL_DATE_PATTERNS = [
    re.compile(r"/(20\d{2})/(\d{2})/(\d{2})(?:/|$)"),       # /YYYY/MM/DD/
    re.compile(r"/(20\d{2})/(\d{2})(\d{2})(?:[A-Z/]|$)"),   # /YYYY/MMDD(后跟字母或/)
    re.compile(r"/(20\d{2})-(\d{2})-(\d{2})(?:/|$)"),       # /YYYY-MM-DD/
    re.compile(r"/[a-z]+/(20\d{2})(\d{2})(\d{2})[A-Z]"),    # /rain/a/20260512A... 腾讯专用
]


def extract_date_from_url(url: str | None) -> datetime | None:
    """从 URL 路径里抽取真实发布日期（spec 002 Bug 3 修复）。

    比 parse_source_date(snippet) 准得多，因为 URL 路径里的日期是网站发布
    时 CMS 写死的，几乎不会改；而 snippet 里第一个出现的 20YY 可能是爬取
    时间、信息更新时间、文章里随手提到的别的日期。

    Returns:
        datetime（UTC）或 None
    """
    if not url:
        return None
    text = str(url)
    for pattern in _URL_DATE_PATTERNS:
        m = pattern.search(text)
        if not m:
            continue
        try:
            y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
            return datetime(y, mo, d, tzinfo=timezone.utc)
        except (ValueError, IndexError):
            continue
    return None


def resolve_published_at(
    url: str | None,
    citation_published_at: Any = None,
    snippet: str | None = None,
) -> datetime | None:
    """spec 002 FR-002：决定 source 的真实发布时间，3 段式优先级。

    1. URL 路径里的日期（最准）—— extract_date_from_url
    2. citation 自带的 published_at / updated_at（Ark 等返回的）
    3. snippet 文本里抽的第一个 20YY-MM-DD（最不可靠的 fallback）

    Returns:
        datetime（UTC）或 None
    """
    return (
        extract_date_from_url(url)
        or parse_source_date(citation_published_at)
        or parse_source_date(snippet)
    )


def iter_dicts(value: Any):
    if isinstance(value, dict):
        yield value
        for item in value.values():
            yield from iter_dicts(item)
    elif isinstance(value, list):
        for item in value:
            yield from iter_dicts(item)


def extract_response_text(result: dict[str, Any]) -> str:
    chunks: list[str] = []
    for item in iter_dicts(result):
        if item.get("type") in {"output_text", "text"} and isinstance(item.get("text"), str):
            chunks.append(item["text"])
        elif isinstance(item.get("content"), str) and item.get("role") == "assistant":
            chunks.append(item["content"])
    if chunks:
        return "\n".join(dict.fromkeys(chunks))
    output_text = result.get("output_text")
    return output_text if isinstance(output_text, str) else ""


def extract_url_citations(result: dict[str, Any]) -> list[dict[str, Any]]:
    citations: list[dict[str, Any]] = []
    for item in iter_dicts(result):
        url = item.get("url") or item.get("source_url")
        if isinstance(url, str) and url.startswith(("http://", "https://")):
            citations.append(item)
    unique: dict[str, dict[str, Any]] = {}
    for citation in citations:
        unique[citation.get("url") or citation.get("source_url")] = citation
    return list(unique.values())


def public_source(source: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": source["id"],
        "title": scrub_internal_source_text(source.get("title") or source.get("domain") or "来源"),
        "url": source.get("url"),
        "domain": source.get("domain"),
        "snippet": scrub_internal_source_text(source.get("snippet")),
        "published_at": source.get("published_at"),
        "updated_at": source.get("updated_at"),
        "reliability_score": source.get("reliability_score", 35),
        # spec-007：透传 source_time 取值途径，供 upsert_ai_places 写 Source.source_time_method
        "source_time_method": source.get("source_time_method"),
    }


def public_source_from_model(source: Source) -> dict[str, Any]:
    return {
        "id": str(source.id),
        "title": scrub_internal_source_text(source.title or source.domain or "来源"),
        "url": source.source_url,
        "domain": source.domain,
        "snippet": scrub_internal_source_text(source.snippet),
        "published_at": source.source_time.date().isoformat() if source.source_time else None,
        "updated_at": None,
        "reliability_score": source.reliability_score,
    }


# FIX: 之前 fallback_center 只查浙江词表，非浙江 query 兜底全部回退到杭州中心
# 导致 amap geocode 失败时 marker 错位（江苏苏州的点落到杭州西湖）
# PROVINCE_CENTERS 含主要省份 + 露营常见城市的中心坐标
PROVINCE_CENTERS: dict[str, tuple[float, float]] = {
    # 江苏：含「市」后缀和无后缀双 key（query 里常没"市"，如"苏州露营"而非"苏州市露营"）
    "江苏省": (32.06, 118.79),
    "苏州市": (31.30, 120.60), "苏州": (31.30, 120.60),
    "南京市": (32.06, 118.79), "南京": (32.06, 118.79),
    "无锡市": (31.49, 120.31), "无锡": (31.49, 120.31),
    "常州市": (31.78, 119.95), "常州": (31.78, 119.95),
    "镇江市": (32.20, 119.45), "镇江": (32.20, 119.45),
    "扬州市": (32.39, 119.42), "扬州": (32.39, 119.42),
    "南通市": (31.98, 120.89), "南通": (31.98, 120.89),
    "徐州市": (34.26, 117.19), "徐州": (34.26, 117.19),
    "太湖": (31.20, 120.20), "阳澄湖": (31.43, 120.83), "虎丘": (31.32, 120.57),
    "上海市": (31.23, 121.47), "上海": (31.23, 121.47), "浦东": (31.22, 121.54),
    "安徽省": (31.86, 117.28),
    "合肥市": (31.86, 117.28), "合肥": (31.86, 117.28),
    "黄山市": (29.71, 118.34), "黄山": (29.71, 118.34),
    "江西省": (28.68, 115.86),
    "南昌市": (28.68, 115.86), "南昌": (28.68, 115.86),
    "庐山": (29.55, 115.99),
    "福建省": (26.07, 119.31),
    "福州市": (26.07, 119.31), "福州": (26.07, 119.31),
    "厦门市": (24.48, 118.09), "厦门": (24.48, 118.09),
    "山东省": (36.65, 117.00),
    "济南市": (36.65, 117.00), "济南": (36.65, 117.00),
    "青岛市": (36.07, 120.38), "青岛": (36.07, 120.38),
    "广东省": (23.13, 113.27),
    "广州市": (23.13, 113.27), "广州": (23.13, 113.27),
    "深圳市": (22.54, 114.05), "深圳": (22.54, 114.05),
    "湖北省": (30.59, 114.30),
    "武汉市": (30.59, 114.30), "武汉": (30.59, 114.30),
    "宜昌市": (30.69, 111.29), "宜昌": (30.69, 111.29),
    "湖南省": (28.21, 112.98),
    "长沙市": (28.21, 112.98), "长沙": (28.21, 112.98),
    "张家界": (29.13, 110.48),
    "四川省": (30.67, 104.07),
    "成都市": (30.67, 104.07), "成都": (30.67, 104.07),
    "九寨沟": (33.27, 103.92),
    "云南省": (25.05, 102.72),
    "昆明市": (25.05, 102.72), "昆明": (25.05, 102.72),
    "大理": (25.61, 100.23), "丽江": (26.86, 100.23),
    "香格里拉": (27.83, 99.71), "西双版纳": (22.01, 100.80),
    "贵州省": (26.65, 106.63),
    "贵阳市": (26.65, 106.63), "贵阳": (26.65, 106.63),
    "陕西省": (34.34, 108.94),
    "西安市": (34.34, 108.94), "西安": (34.34, 108.94),
    "河南省": (34.76, 113.65),
    "郑州市": (34.76, 113.65), "郑州": (34.76, 113.65),
    "洛阳市": (34.62, 112.45), "洛阳": (34.62, 112.45),
    "河北省": (38.04, 114.51),
    "承德": (40.96, 117.94), "秦皇岛": (39.94, 119.60),
    "北京市": (39.90, 116.40), "北京": (39.90, 116.40),
    "怀柔": (40.32, 116.63), "密云": (40.38, 116.84),
    "天津市": (39.08, 117.20), "天津": (39.08, 117.20),
    "内蒙古自治区": (40.82, 111.65),
    "呼伦贝尔": (49.21, 119.76),
    "新疆维吾尔自治区": (43.83, 87.62),
    "乌鲁木齐": (43.83, 87.62), "伊犁": (43.92, 81.32),
    "西藏自治区": (29.65, 91.12),
    "拉萨": (29.65, 91.12), "林芝": (29.65, 94.36),
    "青海省": (36.62, 101.78),
    "西宁": (36.62, 101.78), "青海湖": (36.83, 100.16),
    "甘肃省": (36.06, 103.83),
    "兰州": (36.06, 103.83), "敦煌": (40.14, 94.66),
    "宁夏回族自治区": (38.49, 106.23),
    "银川": (38.49, 106.23),
    "海南省": (20.04, 110.32),
    "海口": (20.04, 110.32), "三亚": (18.25, 109.51),
    "吉林省": (43.82, 125.32),
    "长春": (43.82, 125.32), "长白山": (42.07, 128.05),
    "辽宁省": (41.80, 123.43),
    "沈阳": (41.80, 123.43), "大连": (38.91, 121.61),
    "黑龙江省": (45.80, 126.53),
    "哈尔滨": (45.80, 126.53),
    "大庆市": (46.59, 125.10), "大庆": (46.59, 125.10),
    "齐齐哈尔": (47.35, 123.92),
    "牡丹江": (44.55, 129.61),
    "佳木斯": (46.81, 130.32),
    # 注：漠河故意不加进字典——places.py 的 amap geocoding fallback 测试
    # （test_q_unknown_city_amap_fallback）用它作为「未知城市走 amap」的标志。
    # spec-017 把 amap fallback 推广到 search API 后、漠河会通过 amap 识别。

    # === 补全地级市 + 热门旅游地（用户搜「大庆」识别不到引发的字典补全） ===
    # 吉林（已有长春/长白山）
    "吉林市": (43.84, 126.55), "吉林": (43.84, 126.55),
    "延吉": (42.91, 129.51),

    # 辽宁（已有沈阳/大连）
    "丹东": (40.13, 124.39),
    "鞍山": (41.11, 122.99),

    # 山东（已有济南/青岛）
    "烟台市": (37.46, 121.45), "烟台": (37.46, 121.45),
    "威海市": (37.51, 122.12), "威海": (37.51, 122.12),
    "泰山": (36.27, 117.10),
    "曲阜": (35.59, 116.99),

    # 内蒙古（已有呼伦贝尔）
    "呼和浩特": (40.82, 111.65),
    "阿尔山": (47.18, 119.94),
    "鄂尔多斯": (39.61, 109.78),

    # 新疆（已有乌鲁木齐/伊犁）
    "喀什": (39.47, 75.99),
    "阿勒泰": (47.85, 88.13),

    # 山西（之前完全缺失）
    "山西省": (37.87, 112.55),
    "太原市": (37.87, 112.55), "太原": (37.87, 112.55),
    "平遥": (37.20, 112.18),
    "五台山": (39.04, 113.55),
    "大同": (40.08, 113.30),

    # 河北（之前缺省会石家庄）
    "石家庄市": (38.04, 114.51), "石家庄": (38.04, 114.51),
    "张家口": (40.82, 114.88),

    # 河南（已有郑州/洛阳）
    "开封": (34.80, 114.30),

    # 安徽（已有合肥/黄山）
    "九华山": (30.48, 117.83),

    # 江西（已有南昌/庐山）
    "井冈山": (26.74, 114.28),

    # 湖北（已有武汉/宜昌）
    "神农架": (31.74, 110.68),

    # 湖南（已有长沙/张家界）
    "凤凰": (27.95, 109.60),

    # 福建（已有福州/厦门）
    "泉州": (24.87, 118.68),
    "武夷山": (27.76, 118.04),

    # 广东（已有广州/深圳）
    "珠海": (22.27, 113.58),
    "佛山": (23.02, 113.12),

    # 海南（已有海口/三亚）
    "陵水": (18.51, 110.04),
    "万宁": (18.80, 110.40),

    # 四川（已有成都/九寨沟）
    "乐山": (29.55, 103.77),
    "峨眉山": (29.60, 103.48),
    "稻城": (29.04, 100.30),
    "康定": (30.06, 101.96),

    # 云南（已有昆明/大理/丽江/香格里拉/西双版纳）
    "泸沽湖": (27.71, 100.78),

    # 陕西（已有西安）
    "延安": (36.59, 109.49),

    # 甘肃（已有兰州/敦煌）
    "张掖": (38.93, 100.45),
    "嘉峪关": (39.78, 98.29),

    # 青海（已有西宁/青海湖）
    "茶卡盐湖": (36.74, 99.10),

    # 西藏（已有拉萨/林芝）
    "日喀则": (29.27, 88.88),
    "珠峰": (28.00, 86.92),
}


def fallback_center(query: str) -> tuple[float, float]:
    """amap 失败兜底时的近似中心，按 query 文本智能匹配城市/省份。

    排序优先级：city（市级/具体地名） > province（省级）> 长度长 > 浙江默认。
    避免"江苏省苏州市"被先匹配到的"江苏省"抢走 → 返回南京而非苏州。
    """
    def _specificity(name: str) -> tuple[int, int]:
        # 第一个 key：0=city/地名（更具体），1=province（更泛）
        # 第二个 key：-len（长名优先，更具体）
        is_province = name.endswith("省") or name.endswith("自治区") or (name.endswith("市") and name in {"北京市", "上海市", "天津市", "重庆市"})
        return (1 if is_province else 0, -len(name))

    # 1) 浙江细分（POC 原行为保留：杭州/千岛湖/莫干山等精确）
    for name, coord in sorted(ZHEJIANG_COORDS.items(), key=lambda item: -len(item[0])):
        if name in query:
            return coord
    # 2) 其他省/市细分（city 优先）
    for name, coord in sorted(PROVINCE_CENTERS.items(), key=lambda item: _specificity(item[0])):
        if name in query:
            return coord
    # 3) 用省份关键词推断（覆盖 query 只有省级关键词如"苏南"等场景）
    inferred = _infer_province_from_text(query)
    if inferred and inferred in PROVINCE_CENTERS:
        return PROVINCE_CENTERS[inferred]
    # 4) 全推断失败才回落杭州（POC 默认产品定位）
    return ZHEJIANG_COORDS["杭州"]


def spread_approximate_coord(lat: float, lon: float, seed: str) -> tuple[float, float]:
    digest = int(hashlib.sha256(clean_text(seed).encode()).hexdigest()[:10], 16)
    angle = (digest % 360) * math.pi / 180
    radius_km = 0.8 + ((digest >> 9) % 180) / 100
    lat_offset = math.sin(angle) * radius_km / 111.0
    lon_offset = math.cos(angle) * radius_km / (111.0 * max(math.cos(math.radians(lat)), 0.2))
    return round(lat + lat_offset, 6), round(lon + lon_offset, 6)


def distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    return radius * 2 * math.asin(math.sqrt(a))


def source_time_status_from_models(sources: list[Source]) -> str:
    if not sources:
        return "unknown"
    known = sum(1 for source in sources if source.source_time)
    if known == len(sources):
        return "known"
    return "mixed" if known else "unknown"


async def fallback_ai_search_from_db(
    db: AsyncSession,
    query: str,
    limit: int,
    radius_km: int | None,
    warning: str,
    warning_code: str = "network_error",
) -> dict[str, Any]:
    text = "AI 联网信源暂时不可用，暂未返回可展示的网页来源。请稍后重试，或换一个更具体的地点/需求。"
    return {
        "answer": {"text": text, "sources": []},
        "spots": [],
        "unmapped_candidates": [],
        "sources": [],
        "warning": warning,
        "warning_code": warning_code,
        "provider": {"llm": "local_fallback", "model": "none", "search": "none", "map": "amap"},
        "cache": {"hit": False},
        "metrics": _empty_metrics_block(cache_hit=False),
    }


def _empty_metrics_block(cache_hit: bool) -> dict[str, Any]:
    return {
        "cache_hit": cache_hit,
        "model_id": None,
        "elapsed_seconds": {"search": None, "extract": None, "total": None},
        "tokens": {
            "input": None,
            "output": None,
            "search_input": None,
            "search_output": None,
            "extract_input": None,
            "extract_output": None,
        },
        "cost_cny": None,
    }


def _build_metrics_block(search_metrics, extract_metrics, cache_hit: bool) -> dict[str, Any]:
    """聚合一次搜索（search + extract）的所有可观测指标。

    评测脚手架以这个 dict 为聚合单元——平铺成行写到 csv / db 都能直接用。
    """
    def _attr(obj, name):
        return getattr(obj, name, None) if obj else None

    def _add(a, b):
        if a is None and b is None:
            return None
        return (a or 0) + (b or 0)

    s_elapsed = _attr(search_metrics, "elapsed_seconds")
    e_elapsed = _attr(extract_metrics, "elapsed_seconds")
    s_in = _attr(search_metrics, "input_tokens")
    s_out = _attr(search_metrics, "output_tokens")
    e_in = _attr(extract_metrics, "input_tokens")
    e_out = _attr(extract_metrics, "output_tokens")
    return {
        "cache_hit": cache_hit,
        "model_id": _attr(search_metrics, "model_id") or _attr(extract_metrics, "model_id"),
        "elapsed_seconds": {
            "search": s_elapsed,
            "extract": e_elapsed,
            "total": _add(s_elapsed, e_elapsed),
        },
        "tokens": {
            "input": _add(s_in, e_in),
            "output": _add(s_out, e_out),
            "search_input": s_in,
            "search_output": s_out,
            "extract_input": e_in,
            "extract_output": e_out,
        },
        "cost_cny": _add(_attr(search_metrics, "cost_cny"), _attr(extract_metrics, "cost_cny")),
    }


def sources_from_citations(citations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sources = []
    for index, citation in enumerate(citations, start=1):
        url = citation.get("url") or citation.get("source_url")
        if not url:
            continue
        snippet = clean_text(citation.get("snippet") or citation.get("content") or citation.get("text") or "")
        # spec-006: allow_topic_pages=True 让话题页通过初筛，由下游 _apply_deep_fetch_to_sources 接手深抓
        if not public_fact_source_dict(
            {"url": url, "title": citation.get("title") or citation.get("name"), "snippet": snippet},
            allow_topic_pages=True,
        ):
            continue
        # spec 002 FR-002：3 段式优先级（URL > citation > snippet）
        citation_pub = citation.get("published_at") or citation.get("updated_at")
        date = resolve_published_at(
            url=url,
            citation_published_at=citation_pub,
            snippet=snippet,
        )
        # spec-007 FR-013：分类 source_time 取值途径，写入 source_time_method
        # （meta 途径在下游 attach_meta_times_to_sources 异步 pass 中覆盖）
        if not date:
            time_method = None
        elif extract_date_from_url(url):
            time_method = "url_path"
        elif parse_source_date(citation_pub):
            time_method = "citation"
        else:
            time_method = "snippet"
        sources.append(
            {
                "id": f"s{index:03d}",
                "title": clean_text(citation.get("title") or citation.get("name") or domain_of(url)),
                "url": url,
                "domain": domain_of(url),
                "snippet": snippet[:600],
                "published_at": date.date().isoformat() if date else None,
                "updated_at": None,
                "reliability_score": source_reliability(url, snippet),
                "source_time_method": time_method,
            }
        )
    return sources


async def attach_meta_times_to_sources(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """spec-007：对 source_time 来自 citation/snippet（不可信）或缺失的 source，
    发 HTTP 抓 HTML meta 标签里的真实发布时间，命中则覆盖。

    优先级：url_path（已最优，不动）> meta（本 pass）> citation > snippet。
    只处理 source_time_method ∈ {citation, snippet, None} 的 source。
    并发由 meta_time_service 进程级 Semaphore(5) 控制。

    spec-007 止血逻辑（C 方案 B 部分）：meta 抓取失败时，若原日期来自 citation/snippet
    （已知不可靠，实测污染率高），把 published_at 置空 → 前端显示「信源日期未知」。
    宁可空、不可错——显示一个自信的错日期比显示"未知"更伤产品可信度。
    """
    if not sources:
        return sources
    from app.services.meta_time_service import META_TAG_TO_METHOD, resolve_meta_published_at

    targets = [
        s for s in sources
        if s.get("source_time_method") in (None, "citation", "snippet") and (s.get("url") or s.get("source_url"))
    ]
    if not targets:
        return sources

    async def _enrich(src: dict[str, Any]) -> None:
        url = src.get("url") or src.get("source_url")
        result = await resolve_meta_published_at(str(url))
        if result.status == "matched" and result.published_at:
            src["published_at"] = result.published_at.date().isoformat()
            src["source_time_method"] = META_TAG_TO_METHOD.get(result.source_tag or "", "meta_og")
        elif src.get("source_time_method") in ("citation", "snippet"):
            # meta 抓不到 + 原日期来自不可靠启发式 → 置空，前端显示「日期未知」
            src["published_at"] = None
            src["source_time_method"] = "unverified"

    await asyncio.gather(*[_enrich(s) for s in targets])
    return sources


def attach_answer_dates_to_sources(answer_text: str, sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for source in sources:
        if source.get("published_at") or source.get("updated_at"):
            continue
        windows: list[str] = []
        url = source.get("url")
        if url and (index := answer_text.find(url)) >= 0:
            windows.append(answer_text[max(0, index - 300) : index + len(url) + 80])
        title = clean_text(source.get("title"))
        if title and (index := answer_text.find(title)) >= 0:
            windows.append(answer_text[max(0, index - 160) : index + len(title) + 260])
        for window in windows:
            if date := parse_source_date(window):
                source["published_at"] = date.date().isoformat()
                break
    return sources


def parse_json_object(text: str) -> dict[str, Any]:
    text = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.I)
    text = re.sub(r"\s*```$", "", text.strip())
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{[\s\S]*\}", text)
        if not match:
            raise
        return json.loads(match.group(0))


def cache_key(query: str, limit: int, radius_km: int | None) -> str:
    payload = {
        "query": clean_text(query),
        "limit": limit,
        "radius_km": radius_km,
        "model": settings.ark_model,
        # T7 后续：拒绝话题聚合页 + prompt 要求单帖 URL，bump 版本让旧缓存失效
        # P0-3 上线：阈值分级 + 临时 credibility 公式（1 信源=50→pending_review）
        "version": "mvp-p0-3-threshold-v1",
    }
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def should_cache_response(response: dict[str, Any]) -> bool:
    if response.get("warning"):
        return False
    answer = response.get("answer") if isinstance(response.get("answer"), dict) else {}
    sources = response.get("sources") or answer.get("sources") or []
    return bool(
        clean_text(answer.get("text"))
        or sources
        or response.get("spots")
        or response.get("unmapped_candidates")
    )


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type((httpx.TimeoutException, httpx.HTTPError)),
    reraise=True,
)
async def call_ark_responses(payload: dict[str, Any], timeout: float = 120) -> dict[str, Any]:
    """阻塞调 Ark Responses API（stream 调用走 call_seed_web_answer_stream 不享受重试）。

    P2-6: 自动重试 3 次（网络抖动/超时），指数退避 2s → 4s → 8s（cap 10s）。
    只重试网络层异常；HTTP 4xx/5xx 由代码内 raise RuntimeError 不会重试（避免无限重试鉴权失败等不可恢复错误）。
    """
    if not settings.ark_api_key:
        raise RuntimeError("缺少 ARK_API_KEY")
    headers = {"Authorization": f"Bearer {settings.ark_api_key}", "Content-Type": "application/json"}
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(settings.ark_api_url, headers=headers, json=payload)
            if response.status_code >= 400:
                logger.warning(
                    "ark.http_error",
                    extra={"status": response.status_code, "body_preview": response.text[:200]},
                )
                raise RuntimeError(f"Ark Responses API 返回 {response.status_code}: {response.text[:300]}")
            return response.json()
    except httpx.HTTPError as exc:
        # 由 @retry 装饰捕获并重试；记录给可观测性，不影响重试控制流
        logger.warning("ark.network_error", extra={"err_type": type(exc).__name__, "err": str(exc)[:200]})
        raise


def extract_ark_usage(result: dict[str, Any]) -> dict[str, int | None]:
    """从 Ark Responses API 的返回里提取 token 计数。

    不同 Ark 模型版本字段命名略有差异（input_tokens / prompt_tokens），都尝试一遍。
    """
    usage = result.get("usage") if isinstance(result.get("usage"), dict) else {}
    return {
        "input_tokens": usage.get("input_tokens") or usage.get("prompt_tokens"),
        "output_tokens": usage.get("output_tokens") or usage.get("completion_tokens"),
    }


# 用户面 warning 文案 + 评测分类码
# warning_code 是稳定的字符串，用于评测脚手架聚合统计；warning（文案）面向用户展示。
WARNING_COPY_EMPTY_ANSWER = "AI 这次没找到相关内容；可以换更具体或更小众的关键词再试一次。"
WARNING_COPY_NO_TRACEABLE_SOURCES = (
    "AI 只找到了地图条目或政策汇总页，没有网友实测内容——"
    "建议加入更具体的地名、需求或场景词（如「带电的」「适合床车」），再试一次。"
)
WARNING_COPY_NETWORK_ERROR = (
    "AI 联网检索失败（可能是网络抽风或上游服务异常），请稍后再试，或换一个关键词。"
)
WARNING_COPY_EXTRACT_TIMEOUT = (
    "AI 已找到网页信源，但点位结构化超时了；可以先点开下方信源链接自己查看，"
    "或稍后重试同一搜索。"
)


def _build_seed_search_prompt(query: str, limit: int) -> str:
    """构造 Seed search prompt（call_seed_web_answer / _stream 共用，避免 prompt 漂移）。"""
    target_limit = min(max(limit, 1), 50)
    return (
        "你是自驾游、穷游、露营、床车和房车场景的垂类AI助手。"
        "请联网搜索公开网页，优先选择最近、可追溯、和用户地点强相关的信息源。"
        "回答只做来源事实提炼，不评价真假、不推荐、不打分、不判断是否可信。"
        "回答要短，列出来源里出现的点位或区域线索，不要输出JSON。\n\n"
        f"用户问题：{query}\n\n"
        f"最多列出 {target_limit} 个候选露营/驻车线索。每个候选点必须包含："
        "地点名、地址线索、费用、是否提到可露营/过夜、停车、厕所、水源、信息日期、来源链接。"
        "如果同一来源列出多个具体点位，在数量上限内逐条列出，不要只摘要前一两个。"
        "如果来源没有提到某字段，明确写“来源未提到”。"
        "不要把搜索页、地图入口页、政策汇总页当作事实来源；不要编造坐标、设施或开放状态。"
        "【信源 URL 要求】信源链接必须指向**具体的单条帖子/单篇文章/单条视频**"
        "（如某用户的某条游记、某篇攻略、某条短视频、某条 vlog）。"
        "**禁止使用话题广场页、超话聚合页、hashtag 聚合页、关键词搜索结果页**——"
        "这类页面（典型如标题为「#xxx#」、URL 含 /topic/ 或 /album/、域名为 weitoutiao.zjurl.cn 等）"
        "聚合多条不相关帖子，用户点开后看不到针对某具体地点的实测内容，无法用于求证。"
        "如果某话题页内某条具体帖子相关，应当链接到**该条帖子本身的固定 URL**，而不是话题页。"
    )


def _build_seed_search_payload(query: str, limit: int, stream: bool) -> dict[str, Any]:
    return {
        "model": settings.ark_model,
        "input": [{"role": "user", "content": [{"type": "input_text", "text": _build_seed_search_prompt(query, limit)}]}],
        "tools": [{"type": "web_search"}],
        # 12000 → 4000：模型生成时间和 token 数线性相关。50 个候选 × 平均 30 字 = 1500 字 ≈ 3000 token，
        # 4000 留足缓冲。实测 playground 的常规回答也就 500-1500 token。
        "max_output_tokens": 4000,
        "stream": stream,
    }


def _classify_seed_warnings(answer_text: str, sources: list[dict[str, Any]]) -> tuple[str | None, str | None]:
    if not answer_text:
        return WARNING_COPY_EMPTY_ANSWER, "empty_answer"
    if not sources:
        return WARNING_COPY_NO_TRACEABLE_SOURCES, "no_traceable_sources"
    return None, None


async def call_seed_web_answer(query: str, limit: int) -> tuple[str, list[dict[str, Any]], str | None, str | None, dict[str, Any]]:
    """联网搜索 + 答案抽取（阻塞版，stream=False）。供 /api/v1/ai/search 老链路使用。

    Returns:
        (answer_text, sources, warning_text, warning_code, meta)
    """
    payload = _build_seed_search_payload(query, limit, stream=False)
    start_t = time.perf_counter()
    result = await call_ark_responses(payload, timeout=max(120, LIVE_SEARCH_TIMEOUT_SECONDS + 15))
    elapsed = time.perf_counter() - start_t
    usage = extract_ark_usage(result)
    answer_text = extract_response_text(result).strip()
    sources = attach_answer_dates_to_sources(answer_text, sources_from_citations(extract_url_citations(result)))
    warning_text, warning_code = _classify_seed_warnings(answer_text, sources)
    meta = {
        "elapsed_seconds": round(elapsed, 3),
        "input_tokens": usage["input_tokens"],
        "output_tokens": usage["output_tokens"],
    }
    return answer_text, sources, warning_text, warning_code, meta


async def call_seed_web_answer_stream(query: str, limit: int):
    """7.5-C: Ark stream=True 的 SSE 透传版本。

    Yields:
        (event_type, data) tuples:
        - ("web_search_in_progress", None)     - Ark 开始调 web_search 工具
        - ("web_search_searching", None)       - web_search 正在搜
        - ("web_search_completed", None)       - 搜完，开始生成 answer
        - ("text_delta", str)                  - answer 逐字增量（前端打字机用）
        - ("citation", dict)                   - 原始 annotation 字典（含 url/title 等）
        - ("done", (answer_text, sources, warning_text, warning_code, meta))
          最后一个事件，与 call_seed_web_answer 阻塞版返回值同构
    """
    if not settings.ark_api_key:
        raise RuntimeError("缺少 ARK_API_KEY")
    payload = _build_seed_search_payload(query, limit, stream=True)
    headers = {"Authorization": f"Bearer {settings.ark_api_key}", "Content-Type": "application/json"}

    full_text_parts: list[str] = []
    raw_citations: list[dict[str, Any]] = []
    seen_urls: set[str] = set()
    final_response_obj: dict[str, Any] | None = None
    start_t = time.perf_counter()

    async with httpx.AsyncClient(timeout=max(120, LIVE_SEARCH_TIMEOUT_SECONDS + 15)) as client:
        async with client.stream("POST", settings.ark_api_url, headers=headers, json=payload) as response:
            if response.status_code >= 400:
                body = await response.aread()
                raise RuntimeError(f"Ark stream 返回 {response.status_code}: {body[:300].decode('utf-8', 'ignore')}")

            async for line in response.aiter_lines():
                if not line or not line.startswith("data:"):
                    continue
                raw = line[5:].strip()
                if raw == "[DONE]":
                    break
                try:
                    obj = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                t = obj.get("type")
                if t == "response.web_search_call.in_progress":
                    yield ("web_search_in_progress", None)
                elif t == "response.web_search_call.searching":
                    yield ("web_search_searching", None)
                elif t == "response.web_search_call.completed":
                    yield ("web_search_completed", None)
                elif t == "response.output_text.delta":
                    delta = obj.get("delta") or ""
                    if delta:
                        full_text_parts.append(delta)
                        yield ("text_delta", delta)
                elif t == "response.output_text.annotation.added":
                    annotation = obj.get("annotation") or {}
                    url = annotation.get("url") or annotation.get("source_url")
                    if isinstance(url, str) and url.startswith(("http://", "https://")) and url not in seen_urls:
                        seen_urls.add(url)
                        raw_citations.append(annotation)
                        yield ("citation", annotation)
                elif t == "response.completed":
                    final_response_obj = obj.get("response") or {}

    elapsed = time.perf_counter() - start_t
    answer_text = "".join(full_text_parts).strip()
    sources = attach_answer_dates_to_sources(answer_text, sources_from_citations(raw_citations))
    warning_text, warning_code = _classify_seed_warnings(answer_text, sources)
    usage = extract_ark_usage(final_response_obj or {})
    meta = {
        "elapsed_seconds": round(elapsed, 3),
        "input_tokens": usage["input_tokens"],
        "output_tokens": usage["output_tokens"],
    }
    yield ("done", (answer_text, sources, warning_text, warning_code, meta))


async def call_seed_structured(
    query: str,
    answer_text: str,
    sources: list[dict[str, Any]],
    limit: int,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """结构化抽取。

    Returns:
        (parsed_json, meta)
        meta keys: elapsed_seconds / input_tokens / output_tokens
    """
    target_limit = min(max(limit, 1), 50)
    prompt = {
        "role": "system",
        "task": "把联网回答抽取成地图产品可用JSON。只能依据answer_text和sources抽取，不得编造。",
        "rules": [
            "spots只放具体地名、营地名、村庄/公园/景区内明确点位，不能放文章标题、城市名、搜索词或泛化描述。",
            "同一source可以支撑多个spots；只要answer_text里列出多个点位，就在max_spots内逐条抽取。",
            "source_ids必须来自sources中的id，不能自造。",
            "lat/lon只有在文本或来源明确给出坐标时填写；没有坐标就留空，后端会地理编码。",
            "如果来源描述的是一片区域、路线、河段或村镇附近，而不是精确地址，仍放入spots；address_hint写清区域/路线线索，lat/lon留空，并在risk_tags写“来源描述为区域/路线”。",
            "address_hint 必须包含街道/路/号/村/镇/景区/营地等具体场所；如果来源只到城市级（如'上海'、'杭州'、'市中心'）就放 unmapped_candidates 而不是 spots，避免地图上出现位置不准的 marker。",
            "必须保证界面字段能被对应source支持；来源未提到的设施、费用、过夜信息一律写unknown或来源未提到。",
            "不要推断、不要评价真假、不要推荐、不要打分、不要判断是否可信。",
            "risk_tags只填写来源原文明确提到的限制、禁止、收费、位置模糊等事实备注，不能写AI判断。",
            "unmapped_candidates只放完全无法识别地点名但仍有来源价值的区域/路线线索。",
        ],
        "input": {"query": query, "max_spots": target_limit, "answer_text": answer_text, "sources": sources},
        "output_schema": {
            "spots": [
                {
                    "name": "具体点位名",
                    "province": "省份或unknown",
                    "city": "城市或unknown",
                    "district": "区县或unknown",
                    "address_hint": "地址线索或unknown",
                    "lat": "明确坐标数字，否则null",
                    "lon": "明确坐标数字，否则null",
                    "type": "商业营地/景区露营区/野外露营点/停车露营点/公园草坪/未知",
                    "mentioned_facilities": ["停车", "厕所", "水源"],
                    "mentioned_scenarios": ["自驾", "露营", "过夜"],
                    "price_clues": ["免费/收费/未知"],
                    "positive_summary": "来源事实摘要，不超过90字",
                    "negative_summary": "来源提到的限制或未提到字段，不超过90字",
                    "risk_tags": ["来源明确提到的限制/注意事项"],
                    "source_ids": ["s001"],
                    "reason_for_exclusion": "",
                }
            ],
            "unmapped_candidates": [{"name": "区域或路线线索", "reason": "来源里的位置描述", "source_ids": ["s001"]}],
            "query_summary": "不超过120字",
        },
    }
    payload = {
        "model": settings.ark_model,
        "input": [{"role": "user", "content": [{"type": "input_text", "text": json.dumps(prompt, ensure_ascii=False)}]}],
        # 16000 → 6000：抽取阶段输出是结构化 JSON，假设 50 spots × 100 字字段 = 5000 字 ≈ 10000 token，
        # 实际很少这么多，6000 token 足够覆盖常见 12-20 spots 场景。
        "max_output_tokens": 6000,
        "stream": False,
    }
    start_t = time.perf_counter()
    result = await call_ark_responses(payload, timeout=max(60, STRUCTURED_EXTRACTION_TIMEOUT_SECONDS + 15))
    elapsed = time.perf_counter() - start_t
    usage = extract_ark_usage(result)
    parsed = parse_json_object(extract_response_text(result))
    meta = {
        "elapsed_seconds": round(elapsed, 3),
        "input_tokens": usage["input_tokens"],
        "output_tokens": usage["output_tokens"],
    }
    return parsed, meta


def is_generic_spot_title(name: str) -> bool:
    name = clean_text(name)
    if not name or name in {"营地", "房车营地", "露营地", "公共露营地"}:
        return True
    if any(term in name for term in GENERIC_TERMS + BAD_TERMS):
        return True
    if re.search(r"[市区县镇]免费露营地$", name):
        return True
    return False


def source_date(source: dict[str, Any]) -> datetime | None:
    return parse_source_date(source.get("updated_at") or source.get("published_at"))


def latest_source_date(sources: list[dict[str, Any]]) -> datetime | None:
    dates = [date for source in sources if (date := source_date(source))]
    return max(dates) if dates else None


def source_time_status(sources: list[dict[str, Any]]) -> str:
    if not sources:
        return "unknown"
    known_count = sum(1 for source in sources if source_date(source))
    if known_count == len(sources):
        return "known"
    if known_count == 0:
        return "unknown"
    return "mixed"


def map_fee(price_clues: list[str]) -> str:
    text = " ".join(price_clues)
    if "免费" in text:
        return "free"
    if "低价" in text or "20" in text:
        return "low"
    if "收费" in text:
        return "medium"
    return "unknown"


def map_status(values: list[str], keywords: tuple[str, ...]) -> str:
    text = " ".join(values)
    if any(key in text for key in keywords):
        return "有"
    if "无" in text or "没有" in text:
        return "无"
    return "未知"


# 省份关键词词表：把 query 或 candidate 字段里的地名 → 省份
# 用于 geocode_with_amap 兜底（之前硬编码"浙江省"导致苏州/太湖等查询 marker 落到杭州）
_PROVINCE_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("江苏省", ("江苏", "苏州", "南京", "无锡", "常州", "镇江", "扬州", "泰州", "南通", "盐城", "徐州", "连云港", "淮安", "宿迁", "太湖", "吴江", "昆山", "张家港", "常熟", "虎丘", "阳澄湖")),
    ("浙江省", ("浙江", "杭州", "宁波", "温州", "嘉兴", "湖州", "绍兴", "金华", "衢州", "舟山", "台州", "丽水", "千岛湖", "西湖", "钱塘江", "富春江", "莫干山", "西溪")),
    ("上海市", ("上海", "浦东", "崇明", "青浦", "金山", "奉贤", "嘉定")),
    ("安徽省", ("安徽", "合肥", "黄山", "芜湖", "宣城", "马鞍山", "九华山", "天柱山")),
    ("江西省", ("江西", "南昌", "九江", "庐山", "婺源", "鄱阳湖", "井冈山")),
    ("福建省", ("福建", "福州", "厦门", "泉州", "武夷山", "漳州")),
    ("山东省", ("山东", "济南", "青岛", "烟台", "威海", "泰山", "崂山")),
    ("广东省", ("广东", "广州", "深圳", "珠海", "佛山", "中山", "惠州", "汕头")),
    ("湖北省", ("湖北", "武汉", "宜昌", "襄阳", "三峡", "神农架")),
    ("湖南省", ("湖南", "长沙", "张家界", "凤凰", "衡山")),
    ("四川省", ("四川", "成都", "九寨沟", "峨眉", "稻城", "亚丁", "甘孜")),
    ("云南省", ("云南", "昆明", "大理", "丽江", "香格里拉", "西双版纳", "玉龙雪山")),
    ("贵州省", ("贵州", "贵阳", "黄果树", "梵净山", "镇远", "西江")),
    ("陕西省", ("陕西", "西安", "华山", "秦岭")),
    ("河南省", ("河南", "郑州", "洛阳", "开封", "嵩山")),
    ("河北省", ("河北", "石家庄", "承德", "秦皇岛", "北戴河")),
    ("北京市", ("北京", "海淀", "怀柔", "密云", "延庆", "昌平")),
    ("天津市", ("天津", "蓟州")),
    ("内蒙古自治区", ("内蒙古", "呼伦贝尔", "鄂尔多斯", "锡林郭勒")),
    ("新疆维吾尔自治区", ("新疆", "乌鲁木齐", "喀什", "伊犁", "吐鲁番", "塔克拉玛干", "阿克苏", "阿拉尔", "和田", "库尔勒", "巴音郭楞", "天山", "罗布泊", "尉犁")),
    ("西藏自治区", ("西藏", "拉萨", "林芝", "那曲", "雅鲁藏布", "珠峰", "纳木错", "羊卓雍措", "日喀则", "阿里")),
    ("青海省", ("青海", "西宁", "青海湖", "茶卡")),
    ("甘肃省", ("甘肃", "兰州", "敦煌", "嘉峪关", "张掖")),
    ("宁夏回族自治区", ("宁夏", "银川", "中卫", "沙坡头")),
    ("海南省", ("海南", "海口", "三亚", "亚龙湾")),
    ("吉林省", ("吉林", "长春", "长白山")),
    ("辽宁省", ("辽宁", "沈阳", "大连")),
    ("黑龙江省", ("黑龙江", "哈尔滨", "雪乡", "镜泊湖")),
]


def _infer_province_from_text(*texts: str | None) -> str | None:
    """从任意文本片段（query / name / address_hint 等）推断省份；找不到返 None。"""
    joined = " ".join(t for t in texts if t)
    if not joined:
        return None
    for province, kws in _PROVINCE_KEYWORDS:
        for kw in kws:
            if kw in joined:
                return province
    return None


async def normalize_candidates(ai_result: dict[str, Any], sources: list[dict[str, Any]], query: str, limit: int):
    source_by_id = {source["id"]: source for source in sources if public_fact_source_dict(source)}
    spots: list[dict[str, Any]] = []
    unmapped: list[dict[str, Any]] = []
    seen: set[str] = set()

    for raw in (ai_result.get("spots") or [])[: max(limit * 2, limit)]:
        if not isinstance(raw, dict):
            continue
        name = clean_text(raw.get("name"))
        if not name or name in seen or is_generic_spot_title(name):
            continue
        source_ids = [sid for sid in raw.get("source_ids", []) if sid in source_by_id]
        linked = [source_by_id[sid] for sid in source_ids]
        reason = clean_text(raw.get("reason_for_exclusion"))
        if not source_ids:
            continue
        if reason and any(term in reason for term in ("不满足", "无关", "不是", "禁止", "不符合", "排除")):
            latest = latest_source_date(linked)
            unmapped.append(
                {
                    "name": name,
                    "reason": reason,
                    "latest_source_date": latest.date().isoformat() if latest else None,
                    "source_time_status": source_time_status(linked),
                    "sources": [public_source(item) for item in linked],
                }
            )
            seen.add(name)
            continue

        # spec 005-precise-geocoding: 上游过滤模糊地址（城市级地址 → 直接 unmapped）
        # 避免进入 geocode_with_amap 流程产生市中心 fallback marker
        address_hint = clean_text(raw.get("address_hint"))
        # 只有 raw 也没自带坐标时才检查地址精度（自带精确坐标的优先信任）
        has_raw_coord = raw.get("lat") is not None and raw.get("lon") is not None
        if not has_raw_coord and not _is_precise_address(address_hint):
            latest = latest_source_date(linked)
            unmapped.append(
                {
                    "name": name,
                    "reason": "地址精度不足（只到城市/省份级，无街道/门牌/具体场所）",
                    "address_hint": address_hint or None,
                    "latest_source_date": latest.date().isoformat() if latest else None,
                    "source_time_status": source_time_status(linked),
                    "sources": [public_source(item) for item in linked],
                }
            )
            seen.add(name)
            continue

        lat = raw.get("lat")
        lon = raw.get("lon")
        geo_source = raw.get("geo_source") or "source_coord"
        location_confidence = "high"
        approximate_reason = ""
        try:
            lat = float(lat)
            lon = float(lon)
        except (TypeError, ValueError):
            # FIX: 之前 fallback 写死"浙江省"，导致苏州/南京/北京等非浙江 query 的 marker
            # 全部落到杭州周边。现按 name/address_hint/city/query 智能推断省份。
            inferred_province = (
                clean_text(raw.get("province"))
                or _infer_province_from_text(
                    raw.get("name"),
                    raw.get("address_hint"),
                    raw.get("city"),
                    raw.get("district"),
                    query,
                )
                or "浙江省"  # 全推断失败才回落浙江（保留 POC 默认产品定位）
            )
            geo = await geocode_with_amap(
                name,
                raw.get("address_hint"),
                raw.get("district") or raw.get("city"),
                inferred_province,
            )
            # spec 003-fix-fuzzy-marker (Bug 1 修复):
            # 之前 geocode 失败会用 fallback_center 生成"省份中心"近似坐标，
            # 导致 marker 落到水面 / 远郊（如上海市中心 121.47,31.23 正好在黄浦江）。
            # 用户决策：「信源给的位置就模糊就直接筛掉信源和点位」。
            # 现在：geocode 失败 或 confidence!=high/medium → 进 unmapped，不出 marker。
            if not geo or geo.get("confidence") not in ("high", "medium"):
                latest = latest_source_date(linked)
                unmapped.append(
                    {
                        "name": name,
                        "reason": "位置无法精确识别（geocode 失败或精度过粗）",
                        "latest_source_date": latest.date().isoformat() if latest else None,
                        "source_time_status": source_time_status(linked),
                        "sources": [public_source(item) for item in linked],
                    }
                )
                seen.add(name)
                continue
            lat = geo["lat"]
            lon = geo["lon"]
            geo_source = geo["provider"]
            location_confidence = geo["confidence"]

        latest = latest_source_date(linked)
        price_clues = [clean_text(item) for item in raw.get("price_clues", [])]
        scenarios = [clean_text(item) for item in raw.get("mentioned_scenarios", [])]
        facilities = [clean_text(item) for item in raw.get("mentioned_facilities", [])]
        risk_tags = [clean_text(item) for item in raw.get("risk_tags", []) if item]
        if approximate_reason:
            risk_tags.append(approximate_reason)
        # P0-3 临时 credibility 公式：1 信源=50, 2 信源=75, 3+ 信源=100
        # POC 阶段 AI 搜出的候选 80%+ 是单信源（信源间难 cross-link 到同一点位），
        # 单信源进 pending_review 而非 unmapped，保证地图上有东西；
        # 多信源（≥2）才进 active，作为"主菜单"展示。
        # 真正的多维度字段投票公式在 P2-3 实现，届时覆盖这里。
        credibility_score = min(100, 50 + (len(linked) - 1) * 25) if linked else 0
        if credibility_score < 35:
            # 0 信源候选（理论上 line 742 已 filter 掉，这里是安全网），归 unmapped
            unmapped.append(
                {
                    "name": name,
                    "reason": "无可追溯信源，已作为线索展示但未写入正式库",
                    "latest_source_date": latest.date().isoformat() if latest else None,
                    "source_time_status": source_time_status(linked),
                    "sources": [public_source(item) for item in linked],
                }
            )
            seen.add(name)
            continue
        spot_status = "active" if credibility_score >= 60 else "pending_review"
        spot = {
            "id": None,
            "name": name,
            "type": clean_text(raw.get("type")) or "未知",
            "latitude": round(lat, 6),
            "longitude": round(lon, 6),
            "address": clean_text(raw.get("address_hint")) or None,
            "city": clean_text(raw.get("city")) or None,
            "district": clean_text(raw.get("district")) or None,
            "province": clean_text(raw.get("province")) or _infer_province_from_text(
                raw.get("name"), raw.get("address_hint"), raw.get("city"), raw.get("district"), query,
            ) or "浙江省",
            "location_confidence": location_confidence,
            "geo_source": geo_source,
            "ai_rating": None,
            "credibility_score": credibility_score,
            "recommendation": "caution",
            "source_count": len(linked),
            "price_clues": price_clues or ["未知"],
            "overnight_clues": [item for item in scenarios if "夜" in item or "露营" in item] or ["来源未提到"],
            "toilet_status": map_status(facilities, ("厕所", "公厕", "卫生间")),
            "water_status": map_status(facilities, ("水", "自来水", "水源")),
            "electricity_status": map_status(facilities, ("电", "充电")),
            "vehicle_fit": [],
            "risk_tags": scrub_risk_tags(risk_tags, bool(linked)),
            "positive_summary": scrub_internal_source_text(raw.get("positive_summary")),
            "negative_summary": scrub_internal_source_text(raw.get("negative_summary")),
            "ai_summary": scrub_internal_source_text(raw.get("positive_summary")) or scrub_internal_source_text(raw.get("negative_summary")),
            "last_verified_at": latest.isoformat() if latest else None,
            "latest_source_date": latest.date().isoformat() if latest else None,
            "source_time_status": source_time_status(linked),
            "sources": [public_source(item) for item in linked],
            "status": spot_status,
            # spec-006: 透传深抓的原话题页 URL（若有任何 linked source 命中了深抓）
            "_topic_url_original": next(
                (s.get("_topic_url_original") for s in linked if s.get("_topic_url_original")),
                None,
            ),
        }
        spots.append(spot)
        seen.add(name)
        if len(spots) >= limit:
            break

    for raw in ai_result.get("unmapped_candidates", []) or []:
        if isinstance(raw, dict):
            name = clean_text(raw.get("name"))
            if name and name not in seen:
                source_ids = [sid for sid in raw.get("source_ids", []) if sid in source_by_id]
                linked = [source_by_id[sid] for sid in source_ids]
                latest = latest_source_date(linked)
                unmapped.append(
                    {
                        "name": name,
                        "reason": clean_text(raw.get("reason")) or "定位不足，暂未入图",
                        "latest_source_date": latest.date().isoformat() if latest else None,
                        "source_time_status": source_time_status(linked),
                        "sources": [public_source(item) for item in linked],
                    }
                )
    return spots, unmapped


async def upsert_ai_places(
    db: AsyncSession,
    spots: list[dict[str, Any]],
    query: str,
    data_origin: str = "ai_search",
) -> None:
    """spec-008 起加 data_origin 参数：默认 ai_search（不改既有行为），
    MediaCrawler 导入脚本传 'xhs_crawl' 以标记来源、保持可插拔。"""
    from sqlalchemy import func

    for spot in spots:
        if spot.get("status") not in {"active", "pending_review"}:
            continue
        # 去重键：name + 经纬度近似匹配（~1km 内同名视为同一点位）
        # 旧逻辑只用 name 会让"江边露营"等同名不同地的点位互相覆盖坐标。
        existing = await db.scalar(
            select(Place)
            .where(
                Place.name == spot["name"],
                func.abs(Place.latitude - spot["latitude"]) < 0.01,
                func.abs(Place.longitude - spot["longitude"]) < 0.01,
            )
            .limit(1)
        )
        if existing:
            place = existing
            is_new = False
        else:
            place = Place(name=spot["name"], latitude=spot["latitude"], longitude=spot["longitude"])
            db.add(place)
            is_new = True
        place.type = spot["type"]
        place.latitude = spot["latitude"]
        place.longitude = spot["longitude"]
        place.location = WKTElement(f"POINT({spot['longitude']} {spot['latitude']})", srid=4326)
        place.address = spot.get("address")
        place.city = spot.get("city")
        place.district = spot.get("district")
        place.province = spot.get("province") or "浙江省"
        place.location_confidence = spot.get("location_confidence") or "medium"
        place.geo_source = spot.get("geo_source")
        place.ai_rating = spot.get("ai_rating")
        place.credibility_score = spot.get("credibility_score") or 0
        place.recommendation = spot.get("recommendation") or "caution"
        place.source_count = spot.get("source_count") or 0
        place.price_clues = spot.get("price_clues") or []
        place.overnight_clues = spot.get("overnight_clues") or []
        place.toilet_status = spot.get("toilet_status")
        place.water_status = spot.get("water_status")
        place.electricity_status = spot.get("electricity_status")
        place.vehicle_fit = spot.get("vehicle_fit") or []
        place.risk_tags = spot.get("risk_tags") or []
        place.positive_summary = spot.get("positive_summary")
        place.negative_summary = spot.get("negative_summary")
        place.ai_summary = spot.get("ai_summary")
        place.cached_from_query = query
        # spec-006: 命中深抓时回填原话题页 URL（仅当此次更新带来了新值时）
        if spot.get("_topic_url_original") and not place.topic_url_original:
            place.topic_url_original = spot["_topic_url_original"]
        if is_new:
            place.data_origin = data_origin
        next_status = spot.get("status") or "pending_review"
        place.status = next_status if place.status != "active" or next_status == "active" else place.status
        if spot.get("last_verified_at"):
            place.last_verified_at = datetime.fromisoformat(spot["last_verified_at"])
        await db.flush()
        spot["id"] = str(place.id)
        spot["status"] = place.status
        spot["data_origin"] = place.data_origin
        for source in spot.get("sources", []):
            if not source.get("url"):
                continue
            source_time = parse_source_date(source.get("published_at") or source.get("updated_at"))
            time_method = source.get("source_time_method")  # spec-007
            exists = await db.scalar(select(Source).where(Source.place_id == place.id, Source.source_url == source["url"]).limit(1))
            if exists:
                if source_time and not exists.source_time:
                    exists.source_time = source_time
                # spec-007：meta_* 途径解析的时间更可信，允许覆盖旧值
                if source_time and time_method and time_method.startswith("meta_"):
                    exists.source_time = source_time
                    exists.source_time_method = time_method
                elif time_method == "unverified":
                    # spec-007 止血：原日期不可靠且 meta 抓不到 → 置空旧的错日期
                    exists.source_time = None
                    exists.source_time_method = "unverified"
                elif time_method and not exists.source_time_method:
                    exists.source_time_method = time_method
                if source.get("snippet") and not exists.snippet:
                    exists.snippet = source.get("snippet")
                if source.get("title") and not exists.title:
                    exists.title = source.get("title")
                continue
            db.add(
                Source(
                    place_id=place.id,
                    source_type="公开内容",
                    source_url=source.get("url"),
                    domain=source.get("domain"),
                    title=source.get("title"),
                    snippet=source.get("snippet"),
                    source_time=source_time,
                    source_time_method=time_method,
                    reliability_score=source.get("reliability_score") or 35,
                )
            )
    await db.commit()


# 7.5-D：后台 extract 任务集合
# 模块级 set 防止 asyncio.create_task() 返回的 task 被 GC 取消
_extract_background_tasks: set[asyncio.Task] = set()


def _spawn_extract_task(coro) -> None:
    """启动 extract 后台任务，保留 task 引用，完成后自动从 set 移除。"""
    task = asyncio.create_task(coro)
    _extract_background_tasks.add(task)
    task.add_done_callback(_extract_background_tasks.discard)


async def _run_extract_in_background(
    *,
    query: str,
    answer_text: str,
    sources: list[dict[str, Any]],
    limit: int,
    cache_key_value: str,
    search_metrics: dict[str, Any] | None,
    warning: str | None,
    warning_code: str | None,
    provider_meta: dict[str, str],
    pipeline_start_t: float,
) -> None:
    """7.5-D 后台 extract 任务，独立 db session（不绑定 HTTP request）。

    完成后:
      1. 写 Redis key `extract:result:{cache_key}` TTL 10 分钟（供前端 polling）
      2. 写主 cache_key（让下次同 query cache hit 直接拿完整结果）
    """
    from app.services.providers.registry import get_provider
    from app.database import async_session

    provider = get_provider(settings.search_provider)
    extract_metrics: dict[str, Any] | None = None
    spots: list[dict[str, Any]] = []
    unmapped: list[dict[str, Any]] = []
    failure_code: str | None = None  # None=成功, "extract_timeout", "extract_json_error", "extract_other"

    async def _try_extract_once() -> tuple[dict | None, dict | None]:
        """单次 extract → (ai_result, metrics)；异常向上抛由 caller 分类。"""
        if not (answer_text and sources):
            return {"spots": []}, None
        result = await asyncio.wait_for(
            provider.extract(query, answer_text, sources, limit),
            timeout=STRUCTURED_EXTRACTION_TIMEOUT_SECONDS,
        )
        return result.to_dict(), result.metrics

    # 第一次 extract
    for attempt in (1, 2):
        try:
            ai_result, extract_metrics = await _try_extract_once()
            spots, unmapped = await normalize_candidates(ai_result, sources, query, limit)
            async with async_session() as session:
                try:
                    await upsert_ai_places(session, spots, query)
                except Exception as upsert_exc:  # noqa: BLE001
                    logger.warning(
                        "ai_search.background_upsert_failed",
                        extra={"err_type": type(upsert_exc).__name__, "err": str(upsert_exc)[:200]},
                    )
            failure_code = None
            break  # 成功，不重试
        except json.JSONDecodeError as exc:
            # 7.5-D fix: ARK 偶尔返回脏 JSON（少逗号等）。第 1 次失败就重试 1 次，
            # 第 2 次还坏就放弃，区分 warning_code 让用户知道是格式问题不是超时
            logger.warning(
                "ai_search.background_extract_json_error",
                extra={"attempt": attempt, "query": query, "err": str(exc)[:200]},
            )
            failure_code = "extract_json_error"
            if attempt == 1:
                continue
        except asyncio.TimeoutError as exc:
            logger.warning(
                "ai_search.background_extract_timeout",
                extra={"attempt": attempt, "query": query, "err": str(exc)[:200]},
            )
            failure_code = "extract_timeout"
            break  # timeout 不重试（再来一次大概率还超时）
        except (httpx.HTTPError, RuntimeError, ValueError, NotImplementedError) as exc:
            logger.warning(
                "ai_search.background_extract_other_error",
                extra={"attempt": attempt, "err_type": type(exc).__name__, "query": query, "err": str(exc)[:200]},
            )
            failure_code = "extract_other"
            break

    if failure_code == "extract_timeout":
        final_warning = WARNING_COPY_EXTRACT_TIMEOUT
        final_warning_code = "extract_timeout"
    elif failure_code == "extract_json_error":
        final_warning = "AI 返回的点位结构有格式异常（已重试 1 次）；可以稍后重试同一搜索，或先点开下方信源链接查看原文。"
        final_warning_code = "extract_json_error"
    elif failure_code == "extract_other":
        final_warning = "AI 抽取点位时遇到了未知错误；信源链接仍可点开查看原文，建议稍后重试。"
        final_warning_code = "extract_other"
    else:
        final_warning = warning
        final_warning_code = warning_code
    timeout_hit = failure_code == "extract_timeout"

    extract_done_payload = {
        "ready": True,
        "answer": {"text": answer_text, "sources": [public_source(item) for item in sources]},
        "spots": spots,
        "unmapped_candidates": unmapped,
        "sources": [public_source(item) for item in sources],
        "warning": final_warning,
        "warning_code": final_warning_code,
        "provider": provider_meta,
        "cache": {"hit": False},
        "metrics": _build_metrics_block(search_metrics, extract_metrics, cache_hit=False),
        "extract_timeout": timeout_hit,
    }
    # polling key（TTL 10 分钟够 polling 拿，不污染长缓存）
    await cache_set(f"extract:result:{cache_key_value}", extract_done_payload, ttl_seconds=600)

    # 同时刷主 cache_key 让下次同 query cache hit 拿完整结果
    main_cache_payload = {
        "answer": extract_done_payload["answer"],
        "spots": spots,
        "unmapped_candidates": unmapped,
        "sources": extract_done_payload["sources"],
        "warning": final_warning,
        "warning_code": final_warning_code,
        "provider": provider_meta,
        "cache": {"hit": False},
        "metrics": extract_done_payload["metrics"],
    }
    if should_cache_response(main_cache_payload):
        await cache_set(cache_key_value, main_cache_payload, CACHE_TTL_SECONDS)

    logger.info(
        "ai_search.background_extract_done",
        extra={
            "query": query,
            "outcome": failure_code or "ok",
            "spots": len(spots),
            "unmapped": len(unmapped),
            "took_ms": int((time.perf_counter() - pipeline_start_t) * 1000),
        },
    )


async def ai_search_pipeline_stream(db: AsyncSession, query: str, limit: int = 12, radius_km: int | None = 50):
    """SSE 版本的 pipeline，逐阶段 yield 事件字典。供 /api/v1/search/stream 消费。

    Yields:
        dict with keys: event (str), data (dict)

    事件序列（正常）:
        search_start → [search 阶段] → search_done → extract_start → [extract] → extract_done → complete

    异常分支:
        - 缓存命中: search_start → complete (cache.hit=True)
        - search 失败: search_start → error → complete (fallback from DB)
        - extract 超时: search_start → search_done → extract_start → extract_done(timeout=True) → complete
    """
    # 延迟导入：避免 providers.ark_seed → ai_service 的循环
    from app.services.providers.registry import get_provider

    pipeline_start_t = time.perf_counter()
    logger.info(
        "ai_search.start",
        extra={"query": query, "limit": limit, "radius_km": radius_km, "provider": settings.search_provider},
    )

    # 地理意图识别：从 query 抽出已知地名 → 让前端把地图视野跳过去
    # 延迟 import 避 router/service 循环依赖
    from app.routers.search import _tokenize, detect_place_center
    detected = detect_place_center(query, _tokenize(query))
    search_center_payload: dict | None = None
    detected_place_name: str | None = None
    if detected:
        eff_lat, eff_lon, detected_place_name = detected
        search_center_payload = {"lat": eff_lat, "lon": eff_lon}

    # 立刻推 search_start，让前端关掉等待动画 + 同步搜索中心（地图视野跟随）
    yield {
        "event": "search_start",
        "data": {
            "query": query,
            "limit": limit,
            "search_center": search_center_payload,
            "detected_place": detected_place_name,
        },
    }

    provider = get_provider(settings.search_provider)
    provider_meta = {"llm": provider.name, "model": settings.ark_model, "search": "ark_web_search", "map": "amap"}

    key = cache_key(query, limit, radius_km)
    cached = await cache_get(key)
    if cached:
        cached["cache"] = {"hit": True, "ttl_seconds": CACHE_TTL_SECONDS}
        cached_metrics = cached.get("metrics") or _empty_metrics_block(cache_hit=True)
        cached_metrics["cache_hit"] = True
        cached["metrics"] = cached_metrics
        logger.info(
            "ai_search.cache_hit",
            extra={
                "query": query,
                "spots": len(cached.get("spots") or []),
                "unmapped": len(cached.get("unmapped_candidates") or []),
                "took_ms": int((time.perf_counter() - pipeline_start_t) * 1000),
            },
        )
        yield {"event": "complete", "data": cached}
        return

    # —— search 阶段 ——
    # 7.5-C：对 ark_seed provider 走 stream=True，前端能逐字看到 answer + 信源逐个到达。
    # 其他 provider（deepseek/qwen）暂时走阻塞 fallback 保持向后兼容。
    use_stream_search = settings.search_provider == "ark_seed"

    answer_text: str = ""
    sources: list[dict[str, Any]] = []
    warning: str | None = None
    warning_code: str | None = None
    search_metrics: dict[str, Any] | None = None

    try:
        if use_stream_search:
            # 流式 search：把 Ark 的 SSE 帧逐个透传给前端
            done_payload: tuple[str, list[dict[str, Any]], str | None, str | None, dict[str, Any]] | None = None
            async for inner_event, inner_data in call_seed_web_answer_stream(query, limit):
                if inner_event == "web_search_in_progress":
                    yield {"event": "web_search_in_progress", "data": {}}
                elif inner_event == "web_search_searching":
                    yield {"event": "web_search_searching", "data": {}}
                elif inner_event == "web_search_completed":
                    yield {"event": "web_search_completed", "data": {}}
                elif inner_event == "text_delta":
                    # 7.5-C 关键事件：前端打字机用
                    yield {"event": "text_delta", "data": {"delta": inner_data}}
                elif inner_event == "citation":
                    # 原始 annotation 字典，前端可即时显示信源 chip
                    yield {"event": "citation", "data": inner_data}
                elif inner_event == "done":
                    done_payload = inner_data
            if done_payload is None:
                raise RuntimeError("Ark stream 未返回 done 事件")
            answer_text, sources, warning, warning_code, search_metrics = done_payload
        else:
            search_result = await asyncio.wait_for(provider.search(query, limit), timeout=LIVE_SEARCH_TIMEOUT_SECONDS)
            answer_text = search_result.answer_text
            sources = search_result.sources
            warning = search_result.warning
            warning_code = search_result.warning_code
            search_metrics = search_result.metrics
    except (asyncio.TimeoutError, httpx.HTTPError, RuntimeError, ValueError, NotImplementedError):
        response = await fallback_ai_search_from_db(
            db,
            query=query,
            limit=limit,
            radius_km=radius_km,
            warning=WARNING_COPY_NETWORK_ERROR,
            warning_code="network_error",
        )
        logger.warning(
            "ai_search.done",
            extra={
                "query": query,
                "outcome": "fallback_from_db",
                "warning_code": "network_error",
                "took_ms": int((time.perf_counter() - pipeline_start_t) * 1000),
            },
        )
        yield {"event": "error", "data": {"warning": WARNING_COPY_NETWORK_ERROR, "warning_code": "network_error"}}
        yield {"event": "complete", "data": response}
        return

    # spec-006: 信源深抓 —— 把话题页 source 替换为单帖 / 失败则剔除
    # 必须在 yield search_done 之前完成，让信源 chip 列表与 marker 一致
    sources = await _apply_deep_fetch_to_sources(sources, query)

    # spec-007: 信源时间 meta fallback —— 对 citation/snippet 来源的不可信时间，
    # 抓 HTML meta 真实发布时间覆盖。在深抓之后跑（深抓可能换了 source URL）
    sources = await attach_meta_times_to_sources(sources)

    # search_done：兼容老前端（一次性收 answer + sources）。
    # 新前端可以用 text_delta / citation 增量事件，不再依赖 search_done。
    yield {
        "event": "search_done",
        "data": {
            "answer": {"text": answer_text, "sources": [public_source(item) for item in sources]},
            "sources": [public_source(item) for item in sources],
            "warning": warning,
            "warning_code": warning_code,
            "elapsed_seconds": (search_metrics or {}).get("elapsed_seconds") if isinstance(search_metrics, dict) else None,
        },
    }

    # —— extract 阶段（7.5-D：后台化）——
    # 不再在 SSE 主流里 await extract。原因：
    #   - extract 平均 30-60s，长尾甚至 90s+ 触发 timeout
    #   - 用户已经在 search_done 拿到 answer + 信源，等 extract 期间地图 marker 是次要优化
    # 改造后:
    #   - asyncio.create_task() 后台跑 extract
    #   - 主流立即 yield complete (spots=[], extract_pending=True, extract_cache_key=key)
    #   - 前端拿到 extract_pending=True 后用 /api/v1/search/extract-result/{key} 2s polling
    #   - 后台 task 完成后写 Redis（同步写主 cache_key 让下次 cache hit）
    _spawn_extract_task(
        _run_extract_in_background(
            query=query,
            answer_text=answer_text,
            sources=sources,
            limit=limit,
            cache_key_value=key,
            search_metrics=search_metrics,
            warning=warning,
            warning_code=warning_code,
            provider_meta=provider_meta,
            pipeline_start_t=pipeline_start_t,
        )
    )

    yield {
        "event": "extract_async_started",
        "data": {"extract_cache_key": key, "poll_interval_ms": 2000, "poll_endpoint": f"/api/v1/search/extract-result/{key}"},
    }

    placeholder_response = {
        "answer": {"text": answer_text, "sources": [public_source(item) for item in sources]},
        "spots": [],  # 后台跑，先空；前端 polling 完成后补
        "unmapped_candidates": [],
        "sources": [public_source(item) for item in sources],
        "warning": warning,
        "warning_code": warning_code,
        "provider": provider_meta,
        "cache": {"hit": False},
        "metrics": _build_metrics_block(search_metrics, None, cache_hit=False),
        "extract_pending": True,
        "extract_cache_key": key,
    }
    logger.info(
        "ai_search.done",
        extra={
            "query": query,
            "outcome": "search_done_extract_async",
            "sources": len(sources),
            "took_ms": int((time.perf_counter() - pipeline_start_t) * 1000),
        },
    )
    yield {"event": "complete", "data": placeholder_response}
    return


async def ai_search_pipeline(db: AsyncSession, query: str, limit: int = 12, radius_km: int | None = 50) -> dict[str, Any]:
    """阻塞版兼容入口（/api/v1/ai/search 保留）：复用 stream pipeline 取最终 complete event。

    所有逻辑都在 ai_search_pipeline_stream 里维护，这里只是聚合最终响应。
    """
    final_response: dict[str, Any] | None = None
    async for event in ai_search_pipeline_stream(db, query, limit, radius_km):
        if event["event"] == "complete":
            final_response = event["data"]
    if final_response is None:
        # 兜底：理论上 stream 一定 yield complete；如果没有说明上游 bug
        raise RuntimeError("ai_search_pipeline_stream 未产出 complete 事件")
    return final_response
