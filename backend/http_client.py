import ssl
from urllib.request import HTTPSHandler, ProxyHandler, Request, build_opener

from backend.parser import extract_html_redirect_url


USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125 Safari/537.36"
)


class HttpClient:
    def __init__(self, proxy: str | None, timeout: float = 30.0):
        self.proxy = proxy
        self.timeout = timeout
        context = ssl._create_unverified_context()
        handlers = [HTTPSHandler(context=context)]
        if proxy:
            handlers.append(ProxyHandler({"http": proxy, "https": proxy}))
        self._opener = self._build_opener(*handlers)

    def _build_opener(self, *handlers):
        return build_opener(*handlers)

    def _request(self, url: str) -> Request:
        return Request(url, headers={"User-Agent": USER_AGENT})

    def fetch_html(self, url: str) -> str:
        request = self._request(url)
        with self._opener.open(request, timeout=self.timeout) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            return response.read().decode(charset, errors="replace")

    def resolve_final_url(self, url: str) -> str:
        request = self._request(url)
        with self._opener.open(request, timeout=self.timeout) as response:
            final_url = response.geturl()
            charset = response.headers.get_content_charset() or "utf-8"
            body = response.read().decode(charset, errors="replace")

        html_redirect_url = extract_html_redirect_url(body)
        if html_redirect_url:
            return html_redirect_url
        return final_url
