import unittest
from unittest.mock import patch

from post_chain_crawler import (
    crawl_post_chain,
    fetch_html_via_proxy,
    parse_post_page,
    resolve_url_via_proxy,
)


FIRST_HTML = """
<html>
  <body>
    <h1 class="post-title mb-2 mb-lg-3">第一页标题</h1>
    <div class="btn-group">
      <a href="https://daoyu.fan/goto?down=aaa">在线观看版本</a>
    </div>
    <div class="btn-group">
      <a href="https://daoyu.fan/goto?down=bbb">压缩包版本</a>
      <button data-pwd="weimi.life">密码</button>
    </div>
    <a class="entry-page-next" href="https://daoyu.fan/3200.html">下一篇</a>
  </body>
</html>
"""

SECOND_HTML = """
<html>
  <body>
    <h1 class="post-title mb-2 mb-lg-3">第二页标题</h1>
    <div class="btn-group">
      <a href="https://daoyu.fan/goto?down=ccc">在线观看版本</a>
    </div>
    <a class="entry-page-next" href="/3201.html">下一篇</a>
  </body>
</html>
"""


class PostChainCrawlerTest(unittest.TestCase):
    def test_parse_post_page_extracts_title_second_download_href_and_next_url(self):
        page = parse_post_page(FIRST_HTML, "https://daoyu.fan/3199.html")

        self.assertEqual(page["title"], "第一页标题")
        self.assertEqual(page["download_href"], "https://daoyu.fan/goto?down=bbb")
        self.assertEqual(page["next_url"], "https://daoyu.fan/3200.html")

    def test_parse_post_page_resolves_relative_next_url(self):
        page = parse_post_page(SECOND_HTML, "https://daoyu.fan/3200.html")

        self.assertEqual(page["next_url"], "https://daoyu.fan/3201.html")

    def test_crawl_post_chain_stops_at_max_pages(self):
        html_by_url = {
            "https://daoyu.fan/3199.html": FIRST_HTML,
            "https://daoyu.fan/3200.html": SECOND_HTML,
        }

        pages = crawl_post_chain(
            "https://daoyu.fan/3199.html",
            fetch_html=html_by_url.__getitem__,
            max_pages=1,
        )

        self.assertEqual(len(pages), 1)
        self.assertEqual(pages[0]["url"], "https://daoyu.fan/3199.html")

    def test_crawl_post_chain_resolves_second_download_href(self):
        pages = crawl_post_chain(
            "https://daoyu.fan/3199.html",
            fetch_html=lambda url: FIRST_HTML,
            resolve_url=lambda url: "https://share.feijipan.com/s/QOPtO6IO?code=6666",
            max_pages=1,
        )

        self.assertEqual(
            pages[0]["download_href"],
            "https://daoyu.fan/goto?down=bbb",
        )
        self.assertEqual(
            pages[0]["resolved_download_url"],
            "https://share.feijipan.com/s/QOPtO6IO?code=6666",
        )

    def test_crawl_post_chain_stops_on_seen_next_url(self):
        looping_html = FIRST_HTML.replace(
            'href="https://daoyu.fan/3200.html"',
            'href="https://daoyu.fan/3199.html"',
        )

        pages = crawl_post_chain(
            "https://daoyu.fan/3199.html",
            fetch_html=lambda url: looping_html,
            max_pages=10,
        )

        self.assertEqual(len(pages), 1)

    def test_crawl_post_chain_records_fetch_error_and_stops(self):
        def fetch_html(url):
            if url == "https://daoyu.fan/3199.html":
                return FIRST_HTML
            raise RuntimeError("HTTP Error 502: Bad Gateway")

        pages = crawl_post_chain(
            "https://daoyu.fan/3199.html",
            fetch_html=fetch_html,
            resolve_url=lambda url: "https://share.feijipan.com/s/QOPtO6IO?code=6666",
            max_pages=3,
        )

        self.assertEqual(len(pages), 2)
        self.assertEqual(pages[1]["url"], "https://daoyu.fan/3200.html")
        self.assertEqual(pages[1]["error"], "HTTP Error 502: Bad Gateway")

    @patch("post_chain_crawler.build_opener")
    def test_fetch_html_via_proxy_does_not_pass_context_to_open(self, build_opener):
        response = build_opener.return_value.open.return_value.__enter__.return_value
        response.headers.get_content_charset.return_value = "utf-8"
        response.read.return_value = b"<html></html>"

        html = fetch_html_via_proxy("https://daoyu.fan/3199.html", "http://127.0.0.1:28880")

        self.assertEqual(html, "<html></html>")
        _, kwargs = build_opener.return_value.open.call_args
        self.assertNotIn("context", kwargs)

    @patch("post_chain_crawler.build_opener")
    def test_resolve_url_via_proxy_returns_html_meta_refresh_url(self, build_opener):
        response = build_opener.return_value.open.return_value.__enter__.return_value
        response.headers.get_content_charset.return_value = "utf-8"
        response.read.return_value = (
            b'<html><head><meta http-equiv="refresh" '
            b'content="0;url=https://share.feijipan.com/s/QOPtO6IO?code=6666">'
            b"</head></html>"
        )
        response.geturl.return_value = "https://huanyu-proxy.daoyufan.workers.dev/goto/?down=bbb"

        final_url = resolve_url_via_proxy(
            "https://daoyu.fan/goto?down=bbb",
            "http://127.0.0.1:28880",
        )

        self.assertEqual(final_url, "https://share.feijipan.com/s/QOPtO6IO?code=6666")
        _, kwargs = build_opener.return_value.open.call_args
        self.assertNotIn("context", kwargs)

    @patch("post_chain_crawler.build_opener")
    def test_resolve_url_via_proxy_falls_back_to_redirect_url(self, build_opener):
        response = build_opener.return_value.open.return_value.__enter__.return_value
        response.headers.get_content_charset.return_value = "utf-8"
        response.read.return_value = b"<html></html>"
        response.geturl.return_value = "https://example.com/final"

        final_url = resolve_url_via_proxy(
            "https://daoyu.fan/goto?down=bbb",
            "http://127.0.0.1:28880",
        )

        self.assertEqual(final_url, "https://example.com/final")


if __name__ == "__main__":
    unittest.main()
