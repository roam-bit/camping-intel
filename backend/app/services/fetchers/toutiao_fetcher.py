"""微头条话题页 Playwright fetcher（spec-006 Phase 1）。

实现 PostFetcher 契约：渲染 weitoutiao.zjurl.cn 话题页 SPA，
抽取页内单帖列表的 (title, text_excerpt, published_at, permalink_url)。

注意事项：
- 每次 fetch 新建 browser context（research.md D6：稳定性优先，不复用单例）
- timeout 由调用方控制；超时抛 asyncio.TimeoutError，由上层 fetch_and_match 捕获
- 其它解析/反爬墙错误抛 FetcherError
- 不在 CI 跑（CI 用 FakeFetcher）；上线时需先 `playwright install chromium`
"""
from __future__ import annotations

import asyncio
import re
import urllib.parse
from datetime import datetime

from app.services.fetchers.base import FetcherError, TopicPagePost


# 微头条 SPA 选择器；如果未来改版需要在此调整
# 现状（2026-05）：话题页 a.item-link / div.feed-card 等候选；尽量宽松，多选一
_POST_SELECTORS = [
    "div[class*='feed-card']",
    "div[class*='item-link']",
    "article",
]


class ToutiaoPlaywrightFetcher:
    """微头条 weitoutiao.zjurl.cn 话题页深抓实现。"""

    async def fetch(
        self,
        topic_url: str,
        *,
        timeout_seconds: float = 15.0,
    ) -> list[TopicPagePost]:
        """渲染话题页并抽取候选单帖列表。

        Raises:
            asyncio.TimeoutError: 渲染超时
            FetcherError: 启动 Playwright 失败 / 解析失败
        """
        # 延迟导入：playwright 在不需要时不阻塞模块加载
        try:
            from playwright.async_api import async_playwright, TimeoutError as PWTimeoutError
        except ImportError as exc:
            raise FetcherError(f"playwright 未安装: {exc}") from exc

        try:
            async with async_playwright() as pw:
                browser = await pw.chromium.launch(headless=True)
                context = await browser.new_context(
                    user_agent=(
                        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"
                    ),
                    viewport={"width": 1280, "height": 800},
                )
                page = await context.new_page()
                try:
                    await page.goto(
                        topic_url,
                        timeout=int(timeout_seconds * 1000),
                        wait_until="domcontentloaded",
                    )
                    # 等待动态内容（最多 timeout 一半时间）
                    try:
                        await page.wait_for_selector(
                            ",".join(_POST_SELECTORS),
                            timeout=int(timeout_seconds * 500),
                        )
                    except PWTimeoutError:
                        # 没等到帖子选择器；可能页面结构变了，但 HTML 可能仍含可解析内容
                        pass
                    html = await page.content()
                finally:
                    await context.close()
                    await browser.close()
        except PWTimeoutError as exc:
            raise asyncio.TimeoutError(f"Playwright 超时 {timeout_seconds}s") from exc
        except Exception as exc:
            raise FetcherError(f"Playwright 异常: {type(exc).__name__}: {str(exc)[:200]}") from exc

        return _parse_posts_from_html(html, base_url=topic_url)


def _parse_posts_from_html(html: str, *, base_url: str) -> list[TopicPagePost]:
    """从 HTML 字符串抽取 TopicPagePost 列表。

    解析策略：用正则提取候选单帖卡片片段（不引入 BeautifulSoup 避免新依赖；
    微头条 SPA 现状是把帖子序列化在 window.__SSR_DATA__ 或类似 JSON 块中）。

    实际命中规则需要根据真实页面 HTML 调整；本期保守实现：
    - 优先找 JSON-LD / __INITIAL_STATE__ 等结构化数据
    - 其次找 <a href="/article/...">...</a> 链接 + 邻近文本
    """
    posts: list[TopicPagePost] = []

    # 策略 1：从 SSR 注入的 JSON 抽取（微头条 SPA 常见模式）
    json_match = re.search(
        r"window\.__INITIAL_STATE__\s*=\s*(\{.*?\});\s*(?:</script>|window\.)",
        html,
        re.DOTALL,
    )
    if json_match:
        try:
            import json as _json
            data = _json.loads(json_match.group(1))
            posts.extend(_extract_from_initial_state(data, base_url))
        except (ValueError, KeyError):
            pass

    # 策略 2：fallback HTML link 抽取
    if not posts:
        posts.extend(_extract_from_html_links(html, base_url))

    # 过滤：四字段不全的丢掉
    return [
        p for p in posts
        if p.title.strip() and p.text_excerpt.strip() and p.permalink_url.strip()
    ]


def _extract_from_initial_state(data: dict, base_url: str) -> list[TopicPagePost]:
    """从 __INITIAL_STATE__ 抽 list（具体路径与微头条版本有关，本期尽量宽松）。"""
    results: list[TopicPagePost] = []
    # 常见路径：data["topic"]["posts"] / data["feed"]["items"] / ...
    candidates: list[dict] = []
    for key_path in (
        ("topic", "posts"),
        ("feed", "items"),
        ("data", "list"),
        ("items",),
    ):
        node: object = data
        ok = True
        for key in key_path:
            if isinstance(node, dict) and key in node:
                node = node[key]
            else:
                ok = False
                break
        if ok and isinstance(node, list):
            candidates = node
            break
    for item in candidates:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or item.get("name") or "").strip()
        text = str(item.get("content") or item.get("text") or item.get("abstract") or "").strip()
        url = str(item.get("url") or item.get("share_url") or item.get("permalink") or "").strip()
        if url and not url.startswith("http"):
            url = urllib.parse.urljoin(base_url, url)
        published_at: datetime | None = None
        ts = item.get("publish_time") or item.get("publishTime") or item.get("created_at")
        if isinstance(ts, (int, float)) and ts > 0:
            try:
                published_at = datetime.fromtimestamp(ts if ts < 1e12 else ts / 1000)
            except (ValueError, OverflowError):
                published_at = None
        results.append(TopicPagePost(
            title=title,
            text_excerpt=text[:500],
            published_at=published_at,
            permalink_url=url,
        ))
    return results


def _extract_from_html_links(html: str, base_url: str) -> list[TopicPagePost]:
    """fallback：从 <a href="/article/...">...</a> 抽取（无结构化数据时）。"""
    results: list[TopicPagePost] = []
    # 简陋的链接 + 文本提取；上线后如果命中率低再升级到 BeautifulSoup
    pattern = re.compile(
        r'<a[^>]+href="(?P<url>[^"]+article[^"]+)"[^>]*>(?P<inner>.{20,500}?)</a>',
        re.DOTALL,
    )
    for match in pattern.finditer(html):
        url = match.group("url")
        if not url.startswith("http"):
            url = urllib.parse.urljoin(base_url, url)
        inner_text = re.sub(r"<[^>]+>", "", match.group("inner")).strip()
        if not inner_text:
            continue
        # 粗略：第一行当 title，全文当 excerpt
        lines = [line.strip() for line in inner_text.split("\n") if line.strip()]
        title = lines[0] if lines else inner_text[:80]
        text = "\n".join(lines)
        results.append(TopicPagePost(
            title=title[:200],
            text_excerpt=text[:500],
            published_at=None,
            permalink_url=url,
        ))
    return results
