from __future__ import annotations

import json
import logging
import urllib.parse
from collections.abc import Callable
from dataclasses import dataclass, field
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


TransportCallable = Callable[
    [str, str, bytes | None, dict[str, str], float],
    dict | None,
]

GROUP_TYPES = {"Selector", "Fallback", "URLTest", "LoadBalance", "Relay"}
BUILTIN_TYPES = {"Compatible", "Direct", "Pass", "Reject", "RejectDrop"}
IGNORED_NODE_PREFIXES = ("Traffic:", "Expire:")
logger = logging.getLogger(__name__)


@dataclass(slots=True)
class NikkiProxyRotator:
    api_base: str
    api_secret: str | None
    proxy_group: str
    delay_test_url: str = "https://www.gstatic.com/generate_204"
    delay_timeout_ms: int = 5000
    transport: TransportCallable | None = None
    _cursor: int = field(default=0, init=False)

    def __post_init__(self) -> None:
        self.api_base = self.api_base.rstrip("/")

    def prepare_next_node(self) -> str:
        proxies = self._request("GET", "/proxies")["proxies"]
        members = self._candidate_members(proxies)
        if not members:
            raise RuntimeError(f"no alive nodes in {self.proxy_group}")

        for offset in range(len(members)):
            index = (self._cursor + offset) % len(members)
            node = members[index]
            try:
                delay = self._delay(node)
            except (HTTPError, TimeoutError, URLError) as exc:
                logger.warning("Nikki delay probe failed for %s: %s", node, exc)
                continue
            if delay is not None and delay > 0:
                self._switch(node)
                self._cursor = (index + 1) % len(members)
                return node

        raise RuntimeError(f"no usable nodes in {self.proxy_group}")

    def _candidate_members(self, proxies: dict) -> list[str]:
        group = proxies.get(self.proxy_group)
        if group is None:
            raise RuntimeError(f"Nikki proxy group not found: {self.proxy_group}")

        candidates = []
        for name in group.get("all") or []:
            proxy = proxies.get(name)
            if proxy is None:
                continue
            proxy_type = proxy.get("type")
            if proxy_type in GROUP_TYPES or "all" in proxy:
                continue
            if proxy_type in BUILTIN_TYPES:
                continue
            if name.startswith(IGNORED_NODE_PREFIXES):
                continue
            if not proxy.get("alive"):
                continue
            candidates.append(name)
        return candidates

    def _delay(self, node: str) -> int | None:
        path = "/proxies/{}/delay?timeout={}&url={}".format(
            urllib.parse.quote(node, safe=""),
            self.delay_timeout_ms,
            urllib.parse.quote(self.delay_test_url, safe=""),
        )
        response = self._request(
            "GET",
            path,
            timeout=(self.delay_timeout_ms / 1000) + 3,
        )
        return response.get("delay") if response else None

    def _switch(self, node: str) -> None:
        self._request(
            "PUT",
            f"/proxies/{urllib.parse.quote(self.proxy_group, safe='')}",
            {"name": node},
        )

    def _request(
        self,
        method: str,
        path: str,
        body: dict | None = None,
        timeout: float = 15,
    ) -> dict | None:
        data = json.dumps(body).encode() if body is not None else None
        headers = {"Content-Type": "application/json"}
        if self.api_secret:
            headers["Authorization"] = f"Bearer {self.api_secret}"
        url = f"{self.api_base}{path}"

        if self.transport is not None:
            return self.transport(method, url, data, headers, timeout)

        request = Request(url, data=data, headers=headers, method=method)
        with urlopen(request, timeout=timeout) as response:
            text = response.read().decode("utf-8", errors="replace")
            return json.loads(text) if text else None
