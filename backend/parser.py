import re
from html.parser import HTMLParser
from urllib.parse import urljoin

from download_extractor import extract_download_buttons


HTML_REDIRECT_PATTERNS = [
    re.compile(
        r'<meta[^>]+http-equiv=["\']?refresh["\']?[^>]+content=["\'][^"\']*url=([^"\'>]+)',
        re.IGNORECASE,
    ),
    re.compile(r'location\.replace\(["\']([^"\']+)["\']\)', re.IGNORECASE),
]


class _ArticlePageParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._inside_title = False
        self._title_parts = []
        self.next_href = None

    def handle_starttag(self, tag, attrs):
        attr_map = dict(attrs)
        classes = set((attr_map.get("class") or "").split())

        if tag in {"h1", "h2"} and {"post-title", "mb-2", "mb-lg-3"}.issubset(classes):
            self._inside_title = True
            self._title_parts = []
            return

        if tag == "a" and "entry-page-next" in classes and self.next_href is None:
            self.next_href = attr_map.get("href")

    def handle_endtag(self, tag):
        if tag in {"h1", "h2"} and self._inside_title:
            self._inside_title = False

    def handle_data(self, data):
        if self._inside_title:
            self._title_parts.append(data)

    @property
    def title(self):
        return " ".join("".join(self._title_parts).split())


def parse_article_page(html: str, page_url: str) -> dict[str, object]:
    parser = _ArticlePageParser()
    parser.feed(html)
    parser.close()
    download_hrefs = [
        button["href"]
        for button in extract_download_buttons(html)
        if button.get("href")
    ]

    return {
        "url": page_url,
        "title": parser.title,
        "download_href": download_hrefs[1] if len(download_hrefs) >= 2 else None,
        "resolved_download_url": None,
        "next_url": urljoin(page_url, parser.next_href) if parser.next_href else None,
    }


def extract_html_redirect_url(html: str) -> str | None:
    for pattern in HTML_REDIRECT_PATTERNS:
        match = pattern.search(html)
        if match:
            return match.group(1).strip()
    return None
