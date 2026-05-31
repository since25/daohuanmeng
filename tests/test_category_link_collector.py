import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

import category_link_collector as collector
from category_link_collector import (
    collect_category_links,
    extract_category_links,
    parse_page_range,
)


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

    def test_fetch_html_uses_direct_opener_without_environment_proxy(self):
        response = MagicMock()
        response.__enter__.return_value = response
        response.read.return_value = b"<html>ok</html>"
        opener = MagicMock()
        opener.open.return_value = response

        with (
            patch.object(
                collector,
                "urlopen",
                create=True,
                side_effect=AssertionError("default urlopen should not be used"),
            ),
            patch.object(collector, "ProxyHandler", create=True) as proxy_handler,
            patch.object(
                collector,
                "build_opener",
                create=True,
                return_value=opener,
            ) as build_opener,
        ):
            proxy_handler.return_value = "direct-proxy-handler"

            html = collector.fetch_html("https://daoyu.fan/category/dou-yin-fan-cha/page/1")

        self.assertEqual(html, "<html>ok</html>")
        proxy_handler.assert_called_once_with({})
        build_opener.assert_called_once_with("direct-proxy-handler")
        opener.open.assert_called_once()

    def test_collect_writes_incremental_json_after_each_successful_page(self):
        html_by_url = {
            "https://daoyu.fan/category/dou-yin-fan-cha/page/1": """
            <h2 class="entry-title">
              <a href="https://daoyu.fan/100.html" title="第一页">第一页</a>
            </h2>
            """,
            "https://daoyu.fan/category/dou-yin-fan-cha/page/2": """
            <h2 class="entry-title">
              <a href="https://daoyu.fan/200.html" title="第二页">第二页</a>
            </h2>
            """,
        }

        def fake_fetch(url: str) -> str:
            if url not in html_by_url:
                raise RuntimeError("temporary ssl failure")
            return html_by_url[url]

        with tempfile.TemporaryDirectory() as temp_dir:
            output_path = Path(temp_dir) / "links.json"
            with (
                patch.object(collector, "fetch_html", side_effect=fake_fetch),
                patch.object(collector.time, "sleep"),
            ):
                with self.assertRaisesRegex(RuntimeError, "temporary ssl failure"):
                    collect_category_links(
                        base_url="https://daoyu.fan/category/dou-yin-fan-cha/page/{page}",
                        page_start=1,
                        page_end=3,
                        sleep_seconds=30,
                        output_path=output_path,
                    )

            self.assertEqual(
                json.loads(output_path.read_text(encoding="utf-8")),
                [
                    {
                        "source_page": 1,
                        "title": "第一页",
                        "url": "https://daoyu.fan/100.html",
                    },
                    {
                        "source_page": 2,
                        "title": "第二页",
                        "url": "https://daoyu.fan/200.html",
                    },
                ],
            )


if __name__ == "__main__":
    unittest.main()
