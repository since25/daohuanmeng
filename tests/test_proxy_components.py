import json
import unittest
from types import SimpleNamespace

from mock_origin import build_echo_response
from rewrite_addon import apply_rewrite_to_flow


class ProxyComponentsTest(unittest.TestCase):
    def test_apply_rewrite_to_matching_flow(self):
        flow = SimpleNamespace(
            request=SimpleNamespace(
                url="https://daoyu.fan/path/to/page?x=1",
                scheme="https",
                host="daoyu.fan",
                port=443,
                path="/path/to/page?x=1",
                headers={},
            )
        )

        changed = apply_rewrite_to_flow(flow, block_unrewritten_configured_hosts=False)

        self.assertTrue(changed)
        self.assertEqual(flow.request.scheme, "https")
        self.assertEqual(flow.request.host, "huanyu-proxy.daoyufan.workers.dev")
        self.assertEqual(flow.request.port, 443)
        self.assertEqual(flow.request.path, "/path/to/page?x=1")
        self.assertEqual(flow.request.headers["x-local-rewrite-original-url"], "https://daoyu.fan/path/to/page?x=1")

    def test_apply_rewrite_leaves_static_asset_flow_unchanged(self):
        flow = SimpleNamespace(
            request=SimpleNamespace(
                url="https://daoyu.fan/app.js",
                scheme="https",
                host="daoyu.fan",
                port=443,
                path="/app.js",
                headers={},
            )
        )

        changed = apply_rewrite_to_flow(flow, block_unrewritten_configured_hosts=False)

        self.assertFalse(changed)
        self.assertEqual(flow.request.host, "daoyu.fan")
        self.assertEqual(flow.request.path, "/app.js")
        self.assertEqual(flow.request.headers, {})

    def test_safety_block_intercepts_unrewritten_configured_host(self):
        flow = SimpleNamespace(
            request=SimpleNamespace(url="https://daoyu.fan/app.js"),
            response=None,
        )

        blocked = apply_rewrite_to_flow(flow, block_unrewritten_configured_hosts=True)

        self.assertTrue(blocked)
        self.assertEqual(flow.response.status_code, 599)
        self.assertIn(b"blocked unrewritten configured test host", flow.response.content)

    def test_build_echo_response_contains_request_details(self):
        body = build_echo_response(
            method="GET",
            path="/path/to/page?x=1",
            headers={"Host": "127.0.0.1:9000", "x-local-rewrite-original-url": "https://daoyu.fan/path/to/page?x=1"},
        )

        payload = json.loads(body.decode("utf-8"))

        self.assertEqual(payload["method"], "GET")
        self.assertEqual(payload["path"], "/path/to/page?x=1")
        self.assertEqual(payload["headers"]["x-local-rewrite-original-url"], "https://daoyu.fan/path/to/page?x=1")


if __name__ == "__main__":
    unittest.main()
