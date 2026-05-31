import json
import unittest
from urllib.error import HTTPError
from urllib.parse import parse_qs, unquote, urlsplit

from backend.nikki import NikkiProxyRotator


class FakeNikkiTransport:
    def __init__(self):
        self.calls = []
        self.selected = None
        self.delay_by_node = {}
        self.delay_error_by_node = {}
        self.proxies_payload = {
            "proxies": {
                "daoyufan-resolver-pool": {
                    "type": "Selector",
                    "all": ["node-a", "node-b", "Traffic: 1 GB | 10 GB", "node-c"],
                    "now": "node-a",
                },
                "node-a": {"type": "Vless", "alive": True},
                "node-b": {"type": "Trojan", "alive": True},
                "node-c": {"type": "Vmess", "alive": False},
                "Traffic: 1 GB | 10 GB": {"type": "Trojan", "alive": True},
                "DIRECT": {"type": "Direct", "alive": True},
            }
        }

    def __call__(self, method, url, body=None, headers=None, timeout=None):
        self.calls.append((method, url, body, headers, timeout))
        path = urlsplit(url).path
        query = parse_qs(urlsplit(url).query)
        if method == "GET" and path == "/proxies":
            return self.proxies_payload
        if method == "GET" and path.endswith("/delay"):
            node = unquote(path.split("/")[2])
            if node in self.delay_error_by_node:
                raise self.delay_error_by_node[node]
            return {"delay": self.delay_by_node.get(node, 0)}
        if method == "PUT" and path == "/proxies/daoyufan-resolver-pool":
            self.selected = json.loads(body.decode())["name"]
            return None
        raise AssertionError(f"unexpected request: {method} {url}")


class NikkiProxyRotatorTest(unittest.TestCase):
    def test_selects_first_alive_node_with_positive_delay_and_switches_pool(self):
        transport = FakeNikkiTransport()
        transport.delay_by_node = {"node-a": 0, "node-b": 138}
        rotator = NikkiProxyRotator(
            api_base="http://nikki.example:9090",
            api_secret="secret",
            proxy_group="daoyufan-resolver-pool",
            transport=transport,
        )

        selected = rotator.prepare_next_node()

        self.assertEqual(selected, "node-b")
        self.assertEqual(transport.selected, "node-b")
        self.assertEqual(
            [call[0] for call in transport.calls],
            ["GET", "GET", "GET", "PUT"],
        )
        self.assertEqual(transport.calls[0][3]["Authorization"], "Bearer secret")

    def test_round_robins_after_successful_selection(self):
        transport = FakeNikkiTransport()
        transport.delay_by_node = {"node-a": 100, "node-b": 120}
        rotator = NikkiProxyRotator(
            api_base="http://nikki.example:9090",
            api_secret=None,
            proxy_group="daoyufan-resolver-pool",
            transport=transport,
        )

        first = rotator.prepare_next_node()
        second = rotator.prepare_next_node()

        self.assertEqual(first, "node-a")
        self.assertEqual(second, "node-b")

    def test_skips_node_when_delay_probe_returns_gateway_timeout(self):
        transport = FakeNikkiTransport()
        transport.delay_error_by_node = {
            "node-a": HTTPError(
                url="http://nikki.example:9090/proxies/node-a/delay",
                code=504,
                msg="Gateway Timeout",
                hdrs=None,
                fp=None,
            )
        }
        transport.delay_by_node = {"node-b": 120}
        rotator = NikkiProxyRotator(
            api_base="http://nikki.example:9090",
            api_secret="secret",
            proxy_group="daoyufan-resolver-pool",
            transport=transport,
        )

        selected = rotator.prepare_next_node()

        self.assertEqual(selected, "node-b")
        self.assertEqual(transport.selected, "node-b")


if __name__ == "__main__":
    unittest.main()
