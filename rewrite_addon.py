import os
from types import SimpleNamespace
from urllib.parse import urlsplit

from rewrite_rules import is_configured_host, rewrite_url


def _make_block_response(original_url: str):
    body = (
        "blocked unrewritten configured test host\n"
        f"original-url: {original_url}\n"
    ).encode("utf-8")
    try:
        from mitmproxy import http
    except ImportError:
        return SimpleNamespace(
            status_code=599,
            content=body,
            headers={"content-type": "text/plain; charset=utf-8"},
        )
    return http.Response.make(
        599,
        body,
        {"content-type": "text/plain; charset=utf-8"},
    )


def _should_block_unrewritten_configured_hosts(explicit_value) -> bool:
    if explicit_value is not None:
        return bool(explicit_value)
    return os.environ.get("LOCAL_MITM_BLOCK_UNREWRITTEN", "1") != "0"


def apply_rewrite_to_flow(flow, block_unrewritten_configured_hosts=None) -> bool:
    original_url = flow.request.url
    rewritten = rewrite_url(original_url)
    if rewritten is None:
        if (
            _should_block_unrewritten_configured_hosts(block_unrewritten_configured_hosts)
            and is_configured_host(original_url)
        ):
            flow.response = _make_block_response(original_url)
            return True
        return False

    parsed = urlsplit(rewritten)

    flow.request.scheme = parsed.scheme
    flow.request.host = parsed.hostname or ""
    flow.request.port = parsed.port or (443 if parsed.scheme == "https" else 80)
    flow.request.path = parsed.path or "/"
    if parsed.query:
        flow.request.path = f"{flow.request.path}?{parsed.query}"
    flow.request.headers["x-local-rewrite-original-url"] = original_url
    return True


def request(flow) -> None:
    apply_rewrite_to_flow(flow)
