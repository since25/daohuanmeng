import argparse
import json
import sys
import time
from typing import Callable, Optional
from urllib.request import build_opener

from backend.http_client import HttpClient
from backend.parser import parse_article_page as parse_post_page


class _CliHttpClient(HttpClient):
    def _build_opener(self, *handlers):
        return build_opener(*handlers)


def fetch_html_via_proxy(url: str, proxy: Optional[str], timeout: float = 30.0) -> str:
    return _CliHttpClient(proxy=proxy, timeout=timeout).fetch_html(url)


def resolve_url_via_proxy(url: str, proxy: Optional[str], timeout: float = 30.0) -> str:
    return _CliHttpClient(proxy=proxy, timeout=timeout).resolve_final_url(url)


def crawl_post_chain(
    start_url: str,
    fetch_html: Callable[[str], str],
    resolve_url: Optional[Callable[[str], str]] = None,
    max_pages: int = 3,
    delay_seconds: float = 0.0,
) -> list[dict[str, object]]:
    pages = []
    seen = set()
    current_url = start_url

    while current_url and len(pages) < max_pages and current_url not in seen:
        seen.add(current_url)
        try:
            html = fetch_html(current_url)
        except Exception as exc:
            pages.append(
                {
                    "url": current_url,
                    "title": None,
                    "download_href": None,
                    "resolved_download_url": None,
                    "next_url": None,
                    "error": str(exc),
                }
            )
            break
        page = parse_post_page(html, current_url)
        if resolve_url and page["download_href"]:
            try:
                page["resolved_download_url"] = resolve_url(page["download_href"])
            except Exception as exc:
                page["resolved_download_error"] = str(exc)
        pages.append(page)
        current_url = page["next_url"]
        if current_url and len(pages) < max_pages and current_url not in seen and delay_seconds:
            time.sleep(delay_seconds)

    return pages


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Crawl daoyu.fan post pages and extract title, download hrefs, and next-page href."
    )
    parser.add_argument("--start", default="https://daoyu.fan/3199.html")
    parser.add_argument("--max-pages", type=int, default=3)
    parser.add_argument("--proxy", default="http://127.0.0.1:8080")
    parser.add_argument("--delay", type=float, default=0.5)
    args = parser.parse_args(argv)

    if args.max_pages < 1:
        print("--max-pages must be >= 1", file=sys.stderr)
        return 2

    client = _CliHttpClient(proxy=args.proxy)
    pages = crawl_post_chain(
        args.start,
        fetch_html=client.fetch_html,
        resolve_url=client.resolve_final_url,
        max_pages=args.max_pages,
        delay_seconds=args.delay,
    )
    json.dump(pages, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
