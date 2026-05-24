import argparse
import json
import ssl
import sys
import time
from typing import Callable, Optional
from urllib.request import HTTPSHandler, ProxyHandler, Request, build_opener

from backend.parser import extract_html_redirect_url, parse_article_page as parse_post_page


def fetch_html_via_proxy(url: str, proxy: Optional[str], timeout: float = 30.0) -> str:
    context = ssl._create_unverified_context()
    handlers = [HTTPSHandler(context=context)]
    if proxy:
        handlers.append(ProxyHandler({"http": proxy, "https": proxy}))

    opener = build_opener(*handlers)
    request = Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125 Safari/537.36"
            )
        },
    )
    with opener.open(request, timeout=timeout) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


def resolve_url_via_proxy(url: str, proxy: Optional[str], timeout: float = 30.0) -> str:
    context = ssl._create_unverified_context()
    handlers = [HTTPSHandler(context=context)]
    if proxy:
        handlers.append(ProxyHandler({"http": proxy, "https": proxy}))

    opener = build_opener(*handlers)
    request = Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125 Safari/537.36"
            )
        },
    )
    with opener.open(request, timeout=timeout) as response:
        final_url = response.geturl()
        charset = response.headers.get_content_charset() or "utf-8"
        body = response.read().decode(charset, errors="replace")

    html_redirect_url = extract_html_redirect_url(body)
    if html_redirect_url:
        return html_redirect_url
    return final_url


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

    pages = crawl_post_chain(
        args.start,
        fetch_html=lambda url: fetch_html_via_proxy(url, args.proxy),
        resolve_url=lambda url: resolve_url_via_proxy(url, args.proxy),
        max_pages=args.max_pages,
        delay_seconds=args.delay,
    )
    json.dump(pages, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
