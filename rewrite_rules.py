import re
from typing import Optional
from urllib.parse import urlsplit


DEFAULT_TARGET_BASE = "https://huanyu-proxy.daoyufan.workers.dev"
SURGE_URL_REWRITE_RULE = (
    r"^https?://(?:huanyuxingqiu\.(?:fun|vip|life|com|top|cc|app|xyz|site)|"
    r"daoyu\.(?:fan|com|top)|hyxq\w*\.\w+)/"
    r"(?!.*\.(?:png|jpe?g|gif|webp|svg|ico|css|js|woff2?|ttf|eot|mp[34]|zip|rar)(?:\?|$))(.*)"
)
SURGE_MITM_HOSTNAME_APPEND = (
    "huanyuxingqiu.fun, huanyuxingqiu.vip, huanyuxingqiu.life, "
    "huanyuxingqiu.com, huanyuxingqiu.top, huanyuxingqiu.cc, "
    "huanyuxingqiu.app, huanyuxingqiu.xyz, huanyuxingqiu.site, "
    "daoyu.fan, daoyu.com, daoyu.top, hyxq666.com, hyxq.com"
)

CONFIGURED_HOST_PATTERNS = (
    re.compile(r"^huanyuxingqiu\.(?:fun|vip|life|com|top|cc|app|xyz|site)$"),
    re.compile(r"^daoyu\.(?:fan|com|top)$"),
    re.compile(r"^hyxq\w*\.\w+$"),
)

SURGE_URL_REWRITE_PATTERN = re.compile(
    SURGE_URL_REWRITE_RULE
)


def rewrite_url(url: str, target_base: str = DEFAULT_TARGET_BASE) -> Optional[str]:
    match = SURGE_URL_REWRITE_PATTERN.match(url)
    if match is None:
        return None

    path_and_query = match.group(1)
    return f"{target_base.rstrip('/')}/{path_and_query}"


def is_configured_host(url: str) -> bool:
    hostname = (urlsplit(url).hostname or "").lower()
    return any(pattern.fullmatch(hostname) for pattern in CONFIGURED_HOST_PATTERNS)
