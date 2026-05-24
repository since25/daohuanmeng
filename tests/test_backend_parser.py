import unittest

from backend.parser import extract_html_redirect_url, parse_article_page


ARTICLE_HTML = """
<html>
  <body>
    <h2 class="post-title mb-2 mb-lg-3">Booty徐莉芝 合集</h2>
    <div class="btn-group">
      <a href="https://daoyu.fan/goto?down=first">在线观看</a>
    </div>
    <div class="btn-group">
      <a href="https://daoyu.fan/not-download">无效链接</a>
    </div>
    <div class="btn-group">
      <a href="https://daoyu.fan/goto?down=second">压缩包</a>
    </div>
    <a class="entry-page-next" href="https://daoyu.fan/3200.html">下一篇</a>
  </body>
</html>
"""


RELATIVE_NEXT_HTML = """
<html>
  <body>
    <h1 class="post-title mb-2 mb-lg-3">下一页标题</h1>
    <div class="btn-group">
      <a href="https://daoyu.fan/goto?down=first">在线观看</a>
    </div>
    <div class="btn-group">
      <a href="https://daoyu.fan/goto?down=second">压缩包</a>
    </div>
    <a class="entry-page-next" href="/3201.html">下一篇</a>
  </body>
</html>
"""


class BackendParserTest(unittest.TestCase):
    def test_parse_article_page_extracts_title_second_download_href_and_next_url(self):
        page = parse_article_page(ARTICLE_HTML, "https://daoyu.fan/3199.html")

        self.assertEqual(page["url"], "https://daoyu.fan/3199.html")
        self.assertEqual(page["title"], "Booty徐莉芝 合集")
        self.assertEqual(page["download_href"], "https://daoyu.fan/goto?down=second")
        self.assertEqual(page["next_url"], "https://daoyu.fan/3200.html")
        self.assertIsNone(page["resolved_download_url"])

    def test_parse_article_page_uses_only_download_button_when_single_button_exists(self):
        html = """
        <html>
          <body>
            <h2 class="post-title mb-2 mb-lg-3">单按钮页面</h2>
            <div class="btn-group">
              <a href="https://daoyu.fan/goto?down=only">压缩包</a>
            </div>
          </body>
        </html>
        """

        page = parse_article_page(html, "https://daoyu.fan/4000.html")

        self.assertEqual(page["download_href"], "https://daoyu.fan/goto?down=only")

    def test_parse_article_page_resolves_relative_next_url(self):
        page = parse_article_page(RELATIVE_NEXT_HTML, "https://daoyu.fan/3200.html")

        self.assertEqual(page["next_url"], "https://daoyu.fan/3201.html")

    def test_extract_html_redirect_url_handles_meta_refresh(self):
        html = (
            '<html><head><meta http-equiv="refresh" '
            'content="0;url=https://share.feijipan.com/s/QOPtO6IO?code=6666">'
            "</head></html>"
        )

        self.assertEqual(
            extract_html_redirect_url(html),
            "https://share.feijipan.com/s/QOPtO6IO?code=6666",
        )

    def test_extract_html_redirect_url_handles_location_replace(self):
        html = (
            "<script>"
            'location.replace("https://share.feijipan.com/s/QOPtO6IO?code=6666")'
            "</script>"
        )

        self.assertEqual(
            extract_html_redirect_url(html),
            "https://share.feijipan.com/s/QOPtO6IO?code=6666",
        )


if __name__ == "__main__":
    unittest.main()
