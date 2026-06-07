"""is_topic_aggregator_url 判定逻辑回归测试。

关键防回归点：豆瓣 /group/topic/N/ 是**单帖**（讨论区单贴），不是话题聚合页。
之前 POC 用 `path 含 /topic/` 通用兜底，误把这种 URL 判为聚合页，导致 spec-006 深抓
钩子误删豆瓣单帖信源。修复后取消通用路径匹配，仅留「域名白名单 + 纯 hashtag 标题」。
"""
from __future__ import annotations

from app.services.ai_service import is_topic_aggregator_url


# ─────────────── 应该判为聚合页（True）───────────────

def test_weitoutiao_subdomain_is_aggregator():
    """字节跳动微头条专用子域名 → 聚合页（白名单匹配）。"""
    assert is_topic_aggregator_url("https://weitoutiao.zjurl.cn/topic/4815737") is True
    assert is_topic_aggregator_url("https://weitoutiao.zjurl.cn/any/path") is True


def test_pure_hashtag_title_is_aggregator():
    """标题是纯 hashtag 形式（不管域名）→ 聚合页。"""
    assert is_topic_aggregator_url("https://example.com/x", "#免费露营地#") is True
    assert is_topic_aggregator_url("https://example.com/x", "＃自驾露营＃") is True
    assert is_topic_aggregator_url("https://example.com/x", "【话题】") is True


# ─────────────── 不应判为聚合页（False，关键 regression）───────────────

def test_douban_group_topic_is_NOT_aggregator():
    """❌ regression: 豆瓣 /group/topic/N/ 是讨论单帖（标题为帖子标题），不是聚合页。

    之前用 `path 含 /topic/` 通用兜底误判，导致 spec-006 深抓钩子误删单帖信源。
    """
    url = "https://www.douban.com/group/topic/310901617/"
    title = "日常分享｜西行漫记&DAY66"  # 真实单帖标题，不是 #话题# 形式
    assert is_topic_aggregator_url(url, title) is False


def test_mobile_douban_group_topic_is_NOT_aggregator():
    """同上，移动端 m.douban.com 也不是聚合页。"""
    url = "https://m.douban.com/group/topic/310901617/"
    assert is_topic_aggregator_url(url, "西行漫记") is False


def test_generic_topic_path_is_NOT_aggregator_anymore():
    """❌ regression: 通用 /topic/ 路径不应判为聚合页（取消通用路径匹配）。

    要加新聚合平台，请加进 _TOPIC_AGGREGATOR_DOMAINS 白名单。
    """
    assert is_topic_aggregator_url("https://anywhere.com/topic/123") is False
    assert is_topic_aggregator_url("https://anywhere.com/album/456") is False
    assert is_topic_aggregator_url("https://anywhere.com/superchat/789") is False


def test_normal_article_url_is_NOT_aggregator():
    """普通文章 URL 不应判为聚合页。"""
    assert is_topic_aggregator_url("https://www.zhihu.com/question/12345/answer/67890") is False
    assert is_topic_aggregator_url("https://m.smzdm.com/p/anvpm0e2/") is False
    assert is_topic_aggregator_url("https://post.toutiao.com/article/12345") is False


def test_empty_url_is_NOT_aggregator():
    assert is_topic_aggregator_url(None) is False
    assert is_topic_aggregator_url("") is False
