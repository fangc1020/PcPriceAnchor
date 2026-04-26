"""京东搜索采集器测试 — 覆盖 HTML 解析、价格 API 响应解析。"""

import pytest
from datetime import datetime, timezone

from price_monitor.crawlers.jd.search import JdSearchCrawler
from price_monitor.crawlers.schemas import RawProduct


class TestJdSearchCrawler:
    def setup_method(self):
        self.crawler = JdSearchCrawler()

    def test_yuan_to_fen(self):
        assert JdSearchCrawler._yuan_to_fen("599.00") == 59900
        assert JdSearchCrawler._yuan_to_fen("0.99") == 99
        assert JdSearchCrawler._yuan_to_fen("") == 0
        assert JdSearchCrawler._yuan_to_fen(None) == 0
        assert JdSearchCrawler._yuan_to_fen("abc") == 0

    def test_parse_price_response(self):
        data = [
            {"id": "J_123456", "p": "599.00", "op": "899.00", "m": "549.00"},
            {"id": "J_789012", "p": "299.00"},
        ]
        result = self.crawler._parse_price_response(data)
        assert "123456" in result
        assert result["123456"]["price_fen"] == 59900
        assert result["123456"]["original_fen"] == 89900
        assert result["789012"]["price_fen"] == 29900
        assert result["789012"]["original_fen"] is None

    def test_parse_price_response_empty(self):
        assert self.crawler._parse_price_response([]) == {}

    def test_extract_price_fen(self):
        assert JdSearchCrawler._extract_price_fen("¥599.00") == 59900
        assert JdSearchCrawler._extract_price_fen("$ 299.50") == 29950
        assert JdSearchCrawler._extract_price_fen("no price") == 0

    def test_parse_search_html_empty(self):
        result = self.crawler._parse_search_html("<html><body></body></html>")
        assert result == []

    def test_parse_search_html_with_skus(self):
        html = '''
        <html><body>
        <li data-sku="123456">
            <a title="芝奇 DDR5 6000MHz 32GB(16G×2) CL30 幻锋戟" href="//item.jd.com/123456.html">
        </li>
        <li data-sku="789012">
            <a title="金士顿 DDR4 3200 16GB" href="//item.jd.com/789012.html">
        </li>
        </body></html>
        '''
        result = self.crawler._parse_search_html(html)
        assert len(result) == 2
        assert result[0]["sku_id"] == "123456"
        assert "芝奇" in result[0]["title"]
        assert result[0]["detail_url"] == "https://item.jd.com/123456.html"
        assert result[1]["sku_id"] == "789012"

    def test_platform_code(self):
        assert self.crawler.platform_code == "jd"
