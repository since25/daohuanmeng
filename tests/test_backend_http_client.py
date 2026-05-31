import unittest
from unittest.mock import patch

from backend.http_client import HttpClient


class HttpClientTest(unittest.TestCase):
    @patch("backend.http_client.build_opener")
    def test_fetch_html_returns_decoded_html(self, build_opener):
        response = build_opener.return_value.open.return_value.__enter__.return_value
        response.headers.get_content_charset.return_value = "utf-8"
        response.read.return_value = "<html>第一页</html>".encode("utf-8")

        client = HttpClient(proxy="http://127.0.0.1:28880")
        html = client.fetch_html("https://daoyu.fan/3199.html")

        self.assertEqual(html, "<html>第一页</html>")
        _, kwargs = build_opener.return_value.open.call_args
        self.assertNotIn("context", kwargs)

    @patch("backend.http_client.build_opener")
    def test_resolve_final_url_returns_html_redirect_target(self, build_opener):
        response = build_opener.return_value.open.return_value.__enter__.return_value
        response.headers.get_content_charset.return_value = "utf-8"
        response.read.return_value = (
            b'<html><head><meta http-equiv="refresh" '
            b'content="0;url=https://share.feijipan.com/s/QOPtO6IO?code=6666">'
            b"</head></html>"
        )
        response.geturl.return_value = "https://huanyu-proxy.daoyufan.workers.dev/goto/?down=bbb"

        client = HttpClient(proxy="http://127.0.0.1:28880")
        final_url = client.resolve_final_url("https://daoyu.fan/goto?down=bbb")

        self.assertEqual(final_url, "https://share.feijipan.com/s/QOPtO6IO?code=6666")

    @patch("backend.http_client.build_opener")
    def test_resolve_final_url_does_not_pass_context_to_open(self, build_opener):
        response = build_opener.return_value.open.return_value.__enter__.return_value
        response.headers.get_content_charset.return_value = "utf-8"
        response.read.return_value = b"<html></html>"
        response.geturl.return_value = "https://example.com/final"

        client = HttpClient(proxy="http://127.0.0.1:28880")
        final_url = client.resolve_final_url("https://daoyu.fan/goto?down=bbb")

        self.assertEqual(final_url, "https://example.com/final")
        _, kwargs = build_opener.return_value.open.call_args
        self.assertNotIn("context", kwargs)


if __name__ == "__main__":
    unittest.main()
