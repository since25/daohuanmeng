from __future__ import annotations

import argparse
import json
import time
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.parse import urljoin
from urllib.request import ProxyHandler, Request, build_opener


class _CategoryLinkParser(HTMLParser):
    def __init__(self, page_url: str, source_page: int):
        super().__init__(convert_charrefs=True)
        self.page_url = page_url
        self.source_page = source_page
        self._entry_title_depth = 0
        self._current_link: dict[str, Any] | None = None
        self._current_text: list[str] = []
        self.links: list[dict[str, Any]] = []

    def handle_starttag(self, tag, attrs):
        attr_map = dict(attrs)
        classes = set((attr_map.get("class") or "").split())
        if tag == "h2" and "entry-title" in classes:
            self._entry_title_depth += 1
            return

        if self._entry_title_depth <= 0:
            return

        if tag == "h2":
            self._entry_title_depth += 1
            return

        if tag == "a" and self._current_link is None:
            href = attr_map.get("href")
            if not href:
                return
            self._current_link = {
                "source_page": self.source_page,
                "title": attr_map.get("title") or "",
                "url": urljoin(self.page_url, href),
            }
            self._current_text = []

    def handle_endtag(self, tag):
        if self._entry_title_depth <= 0:
            return

        if tag == "a" and self._current_link is not None:
            text_title = " ".join("".join(self._current_text).split())
            if text_title:
                self._current_link["title"] = text_title
            self.links.append(self._current_link)
            self._current_link = None
            self._current_text = []
            return

        if tag == "h2":
            self._entry_title_depth -= 1

    def handle_data(self, data):
        if self._current_link is not None:
            self._current_text.append(data)


def extract_category_links(html: str, *, page_url: str, source_page: int) -> list[dict[str, Any]]:
    parser = _CategoryLinkParser(page_url=page_url, source_page=source_page)
    parser.feed(html)
    parser.close()
    return parser.links


def fetch_html(url: str, *, timeout: float = 20) -> str:
    request = Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
            )
        },
    )
    opener = build_opener(ProxyHandler({}))
    with opener.open(request, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="replace")


def parse_page_range(value: str) -> tuple[int, int]:
    parts = value.split(":", 1)
    if len(parts) != 2:
        raise ValueError("page range must use START:END format")
    start = int(parts[0])
    end = int(parts[1])
    if start < 1 or end < start:
        raise ValueError("page range end must be greater than or equal to start")
    return start, end


def collect_category_links(
    *,
    base_url: str,
    page_start: int,
    page_end: int,
    sleep_seconds: float,
) -> list[dict[str, Any]]:
    collected: list[dict[str, Any]] = []
    for page in range(page_start, page_end + 1):
        page_url = base_url.format(page=page)
        html = fetch_html(page_url)
        collected.extend(
            extract_category_links(html, page_url=page_url, source_page=page)
        )
        if page < page_end and sleep_seconds > 0:
            time.sleep(sleep_seconds)
    return collected


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Collect daoyu.fan category entry title links into JSON."
    )
    parser.add_argument(
        "--base-url",
        default="https://daoyu.fan/category/dou-yin-fan-cha/page/{page}",
        help="Category URL template. Use {page} as the page placeholder.",
    )
    parser.add_argument("--page-start", type=int)
    parser.add_argument("--page-end", type=int)
    parser.add_argument("--page-range", help="Page range in START:END format, for example 1:35.")
    parser.add_argument("--sleep", type=float, default=2.0)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)

    if args.page_range:
        try:
            page_start, page_end = parse_page_range(args.page_range)
        except ValueError as exc:
            parser.error(str(exc))
    else:
        if args.page_end is None:
            parser.error("--page-end is required when --page-range is not provided")
        if args.page_start is None:
            parser.error("--page-start is required when --page-range is not provided")
        page_start = args.page_start
        page_end = args.page_end
        if page_start < 1 or page_end < page_start:
            parser.error("--page-end must be greater than or equal to --page-start")

    links = collect_category_links(
        base_url=args.base_url,
        page_start=page_start,
        page_end=page_end,
        sleep_seconds=args.sleep,
    )
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(links, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {len(links)} links to {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
