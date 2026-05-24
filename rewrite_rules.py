import re
from typing import Optional
from urllib.parse import urlsplit


DEFAULT_TARGET_BASE = "https://huanyu-proxy.daoyufan.workers.dev"
CONFIGURED_HOSTS = {
    "daoyu.fan",
    "huanyuxingqiu.vip",
    "huanyuxingqiu.life",
    "hyxq666.com",
}

SURGE_URL_REWRITE_PATTERN = re.compile(
    r"^https?://"
    r"(?:daoyu\.fan|huanyuxingqiu\.(?:vip|life)|hyxq666\.com)"
    r"/"
    r"(?!.*\.(?:png|jpe?g|gif|webp|svg|ico|css|js|woff2?|ttf|eot|mp[34]|zip|rar)(?:\?|$))"
    r"(.*)"
)


def rewrite_url(url: str, target_base: str = DEFAULT_TARGET_BASE) -> Optional[str]:
    match = SURGE_URL_REWRITE_PATTERN.match(url)
    if match is None:
        return None

    path_and_query = match.group(1)
    return f"{target_base.rstrip('/')}/{path_and_query}"


def is_configured_host(url: str) -> bool:
    return (urlsplit(url).hostname or "").lower() in CONFIGURED_HOSTS
