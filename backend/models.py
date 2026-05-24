from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class StartJobOptions:
    start_url: str
    max_pages: int
    delay_seconds: float
    proxy: str | None
    resolve_final_url: bool
    skip_cached_articles: bool
    use_resolver_cache: bool
    resolver_proxy: str | None = None
    rewrite_resolver_url: bool = False
    nikki_api_base: str | None = None
    nikki_api_secret: str | None = None
    nikki_proxy_group: str | None = None
    nikki_delay_test_url: str = "https://www.gstatic.com/generate_204"
    nikki_delay_timeout_ms: int = 5000
