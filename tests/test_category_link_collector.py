import unittest

from category_link_collector import extract_category_links, parse_page_range


class CategoryLinkCollectorTest(unittest.TestCase):
    def test_parses_manual_page_range(self):
        self.assertEqual(parse_page_range("1:35"), (1, 35))

    def test_extracts_entry_title_links_with_source_page(self):
        html = """
        <html>
          <body>
            <h2 class="entry-title">
              <a target="_blank" href="https://daoyu.fan/45790.html" title="宫徵羽合集">宫徵羽合集</a>
            </h2>
            <h2 class="entry-title">
              <a target="_blank" href="/45800.html" title="第二个标题">第二个标题</a>
            </h2>
          </body>
        </html>
        """

        links = extract_category_links(
            html,
            page_url="https://daoyu.fan/category/dou-yin-fan-cha/page/2",
            source_page=2,
        )

        self.assertEqual(
            links,
            [
                {
                    "source_page": 2,
                    "title": "宫徵羽合集",
                    "url": "https://daoyu.fan/45790.html",
                },
                {
                    "source_page": 2,
                    "title": "第二个标题",
                    "url": "https://daoyu.fan/45800.html",
                },
            ],
        )


if __name__ == "__main__":
    unittest.main()
