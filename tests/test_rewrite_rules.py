import unittest

from rewrite_rules import is_configured_host, rewrite_url


class RewriteRulesTest(unittest.TestCase):
    def test_rewrites_matching_domain_to_worker_target(self):
        rewritten = rewrite_url(
            "https://daoyu.fan/api/v1/member/profile?token=local-test"
        )

        self.assertEqual(
            rewritten,
            "https://huanyu-proxy.daoyufan.workers.dev/api/v1/member/profile?token=local-test",
        )

    def test_can_override_target_base_for_local_mock_tests(self):
        rewritten = rewrite_url(
            "https://daoyu.fan/api/v1/member/profile?token=local-test",
            target_base="http://127.0.0.1:9000",
        )

        self.assertEqual(
            rewritten,
            "http://127.0.0.1:9000/api/v1/member/profile?token=local-test",
        )

    def test_rewrites_all_configured_domains(self):
        urls = [
            "https://huanyuxingqiu.fun/root",
            "https://huanyuxingqiu.vip/a",
            "https://huanyuxingqiu.life/b",
            "https://huanyuxingqiu.com/c",
            "https://huanyuxingqiu.top/d",
            "https://huanyuxingqiu.cc/e",
            "https://huanyuxingqiu.app/f",
            "https://huanyuxingqiu.xyz/g",
            "https://huanyuxingqiu.site/h",
            "https://daoyu.com/i",
            "https://daoyu.top/j",
            "https://hyxq666.com/k",
            "https://hyxq.com/m",
            "https://hyxqabc.net/n",
        ]

        self.assertEqual(
            [rewrite_url(url) for url in urls],
            [
                "https://huanyu-proxy.daoyufan.workers.dev/root",
                "https://huanyu-proxy.daoyufan.workers.dev/a",
                "https://huanyu-proxy.daoyufan.workers.dev/b",
                "https://huanyu-proxy.daoyufan.workers.dev/c",
                "https://huanyu-proxy.daoyufan.workers.dev/d",
                "https://huanyu-proxy.daoyufan.workers.dev/e",
                "https://huanyu-proxy.daoyufan.workers.dev/f",
                "https://huanyu-proxy.daoyufan.workers.dev/g",
                "https://huanyu-proxy.daoyufan.workers.dev/h",
                "https://huanyu-proxy.daoyufan.workers.dev/i",
                "https://huanyu-proxy.daoyufan.workers.dev/j",
                "https://huanyu-proxy.daoyufan.workers.dev/k",
                "https://huanyu-proxy.daoyufan.workers.dev/m",
                "https://huanyu-proxy.daoyufan.workers.dev/n",
            ],
        )

    def test_does_not_rewrite_static_assets_excluded_by_surge_rule(self):
        static_urls = [
            "https://daoyu.fan/app.js",
            "https://huanyuxingqiu.fun/logo.png",
            "https://daoyu.fan/logo.png?version=1",
            "https://huanyuxingqiu.vip/font.woff2",
            "https://hyxq666.com/archive.zip",
        ]

        self.assertEqual([rewrite_url(url) for url in static_urls], [None] * 5)

    def test_does_not_rewrite_unmatched_domain(self):
        self.assertIsNone(rewrite_url("https://example.com/api/v1/member/profile"))

    def test_detects_configured_test_hosts(self):
        self.assertTrue(is_configured_host("https://huanyuxingqiu.fun/app.js"))
        self.assertTrue(is_configured_host("https://daoyu.fan/app.js"))
        self.assertTrue(is_configured_host("https://daoyu.com/app.js"))
        self.assertTrue(is_configured_host("https://huanyuxingqiu.life/api"))
        self.assertTrue(is_configured_host("https://hyxq.com/api"))
        self.assertTrue(is_configured_host("https://hyxqabc.net/api"))
        self.assertFalse(is_configured_host("https://example.com/api"))


if __name__ == "__main__":
    unittest.main()
