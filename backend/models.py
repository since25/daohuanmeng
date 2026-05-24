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
