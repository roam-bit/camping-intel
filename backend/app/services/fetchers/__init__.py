"""信源深度抓取 fetcher 子包（spec-006 Phase 1）。

模块边界：
- base.py: TopicPagePost dataclass + PostFetcher Protocol + FetcherError
- toutiao_fetcher.py: 微头条话题页 Playwright 实现
- fake_fetcher.py: 测试用 stub（可选；测试也可在 test 文件内 inline 定义）

后续 Phase 2 扩展知乎/小红书时，再加 zhihu_fetcher.py / xhs_fetcher.py，
所有 fetcher 实现同一个 PostFetcher Protocol。
"""
from app.services.fetchers.base import FetcherError, PostFetcher, TopicPagePost

__all__ = ["FetcherError", "PostFetcher", "TopicPagePost"]
