import argparse
import json
import re
import sys
from html.parser import HTMLParser
from typing import Optional


def _class_list(attrs: dict[str, Optional[str]]) -> set[str]:
    return set((attrs.get("class") or "").split())


def _is_download_href(href: Optional[str]) -> bool:
    return bool(href and "/goto?down=" in href)


class _DownloadButtonParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self._group_depth = 0
        self._current_link = None
        self._inside_link = False
        self._current_link_text = []
        self._current_password = None
        self._buttons = []

    def handle_starttag(self, tag, attrs):
        attr_map = dict(attrs)
        classes = _class_list(attr_map)

        if tag == "div" and "btn-group" in classes:
            self._group_depth += 1
            self._current_link = None
            self._inside_link = False
            self._current_link_text = []
            self._current_password = None
            return

        if self._group_depth == 0:
            return

        if tag == "div":
            self._group_depth += 1
            return

        if tag == "a" and _is_download_href(attr_map.get("href")):
            self._current_link = attr_map.get("href")
            self._inside_link = True
            self._current_link_text = []
            return

        if tag == "button" and "copy-pwd" in classes:
            self._current_password = attr_map.get("data-pwd")

    def handle_endtag(self, tag):
        if self._group_depth == 0:
            return

        if tag == "a" and self._current_link:
            self._inside_link = False
            return

        if tag == "div":
            self._group_depth -= 1
            if self._group_depth == 0 and self._current_link:
                self._buttons.append(
                    {
                        "href": self._current_link,
                        "text": re.sub(r"\s+", " ", "".join(self._current_link_text)).strip(),
                        "password": self._current_password,
                    }
                )
                self._current_link = None
                self._inside_link = False
                self._current_link_text = []
                self._current_password = None

    def handle_data(self, data):
        if self._group_depth and self._inside_link:
            self._current_link_text.append(data)

    @property
    def buttons(self):
        return self._buttons


def extract_download_buttons(html: str) -> list[dict[str, Optional[str]]]:
    parser = _DownloadButtonParser()
    parser.feed(html)
    parser.close()
    return parser.buttons


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Extract daoyu.fan download button groups from an HTML file."
    )
    parser.add_argument("html_file", nargs="?", help="HTML file path. Reads stdin when omitted.")
    args = parser.parse_args(argv)

    if args.html_file:
        with open(args.html_file, "r", encoding="utf-8", errors="replace") as html_file:
            html = html_file.read()
    else:
        html = sys.stdin.read()

    json.dump(extract_download_buttons(html), sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
