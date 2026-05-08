from html import unescape
from html.parser import HTMLParser
from urllib.parse import parse_qs, urlencode, urlparse

import httpx

import database


USER_AGENT = "AI Blueprint/1.0 (+local user initiated request)"
MAX_WEB_BYTES = 2_000_000


class TextExtractor(HTMLParser):
    def __init__(self):
        super().__init__()
        self.title = ""
        self._in_title = False
        self._skip = 0
        self._parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag == "title":
            self._in_title = True
        if tag in {"script", "style", "noscript", "svg", "canvas"}:
            self._skip += 1

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag == "title":
            self._in_title = False
        if tag in {"script", "style", "noscript", "svg", "canvas"} and self._skip:
            self._skip -= 1
        if tag in {"p", "div", "section", "article", "li", "br", "h1", "h2", "h3"}:
            self._parts.append("\n")

    def handle_data(self, data):
        text = " ".join(data.split())
        if not text:
            return
        if self._in_title:
            self.title = f"{self.title} {text}".strip()
        elif not self._skip:
            self._parts.append(text)

    def text(self) -> str:
        lines = []
        for line in " ".join(self._parts).split("\n"):
            clean = " ".join(line.split())
            if clean:
                lines.append(clean)
        return "\n\n".join(lines)


class DuckDuckGoResultParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.results: list[dict] = []
        self._active_link: dict | None = None
        self._active_snippet = False
        self._snippet_parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        classes = attrs_dict.get("class", "")
        if tag == "a" and "result__a" in classes:
            self._active_link = {"title": "", "url": attrs_dict.get("href", "")}
        elif "result__snippet" in classes:
            self._active_snippet = True
            self._snippet_parts = []

    def handle_endtag(self, tag):
        if tag == "a" and self._active_link:
            self.results.append(self._active_link)
            self._active_link = None
        elif self._active_snippet:
            self._active_snippet = False
            if self.results:
                self.results[-1]["snippet"] = " ".join(self._snippet_parts).strip()

    def handle_data(self, data):
        text = " ".join(data.split())
        if not text:
            return
        if self._active_link is not None:
            self._active_link["title"] = f"{self._active_link['title']} {text}".strip()
        elif self._active_snippet:
            self._snippet_parts.append(text)


def validate_http_url(url: str) -> str:
    parsed = urlparse(url.strip())
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Use a valid http or https URL.")
    return parsed.geturl()


async def fetch_page_text(url: str) -> dict:
    url = validate_http_url(url)
    async with httpx.AsyncClient(
        follow_redirects=True,
        timeout=httpx.Timeout(20.0, connect=8.0),
        headers={"User-Agent": USER_AGENT, "Accept": "text/html, text/plain;q=0.9,*/*;q=0.5"},
    ) as client:
        response = await client.get(url)
        response.raise_for_status()
        content = response.content[:MAX_WEB_BYTES]
        content_type = response.headers.get("content-type", "")

    text = content.decode(response.encoding or "utf-8", errors="replace")
    if "html" in content_type.lower() or "<html" in text[:1000].lower():
        parser = TextExtractor()
        parser.feed(text)
        title = parser.title or urlparse(str(response.url)).netloc
        extracted = parser.text()
    else:
        title = urlparse(str(response.url)).netloc
        extracted = "\n".join(line.strip() for line in text.splitlines() if line.strip())

    if not extracted:
        raise ValueError("No readable text found at this URL.")

    return {
        "url": str(response.url),
        "title": title[:180],
        "text": extracted[:200_000],
        "size_bytes": len(extracted.encode("utf-8")),
    }


async def web_search(query: str, count: int = 5) -> list[dict]:
    searxng_base_url = database.get_setting("searxng_base_url").strip().rstrip("/")
    if searxng_base_url:
        try:
            results = await _search_searxng(searxng_base_url, query, count)
            if results:
                return results
        except Exception:
            pass

    key = database.get_setting("brave_search_api_key")
    if key:
        return await _search_brave(key, query, count)

    return await _search_duckduckgo(query, count)


async def _search_brave(key: str, query: str, count: int) -> list[dict]:
    params = {"q": query, "count": max(1, min(count, 10)), "text_decorations": "false"}
    async with httpx.AsyncClient(timeout=20.0, headers={"X-Subscription-Token": key, "Accept": "application/json"}) as client:
        response = await client.get("https://api.search.brave.com/res/v1/web/search", params=params)
        response.raise_for_status()
        data = response.json()

    results = []
    for item in (data.get("web", {}).get("results") or [])[:count]:
        url = item.get("url") or ""
        title = item.get("title") or url
        description = item.get("description") or ""
        if not url:
            continue
        results.append({
            "title": title,
            "url": url,
            "snippet": description,
            "source": urlparse(url).netloc,
        })
    return results


async def _search_searxng(base_url: str, query: str, count: int) -> list[dict]:
    params = {"q": query, "format": "json", "language": "en", "safesearch": 1}
    async with httpx.AsyncClient(timeout=20.0, headers={"User-Agent": USER_AGENT, "Accept": "application/json"}) as client:
        response = await client.get(f"{base_url}/search", params=params)
        response.raise_for_status()
        data = response.json()

    results = []
    for item in (data.get("results") or [])[:count]:
        url = item.get("url") or ""
        title = item.get("title") or url
        snippet = item.get("content") or ""
        if not url:
            continue
        results.append({"title": title, "url": url, "snippet": snippet, "source": urlparse(url).netloc})
    return results


async def _search_duckduckgo(query: str, count: int) -> list[dict]:
    params = urlencode({"q": query})
    async with httpx.AsyncClient(
        follow_redirects=True,
        timeout=20.0,
        headers={"User-Agent": USER_AGENT, "Accept": "text/html"},
    ) as client:
        response = await client.get(f"https://html.duckduckgo.com/html/?{params}")
        response.raise_for_status()

    parser = DuckDuckGoResultParser()
    parser.feed(response.text)
    results = []
    for item in parser.results[:count]:
        url = _clean_duckduckgo_url(item.get("url", ""))
        if not url:
            continue
        results.append({
            "title": unescape(item.get("title") or url),
            "url": url,
            "snippet": unescape(item.get("snippet", "")),
            "source": urlparse(url).netloc,
        })
    if not results:
        raise ValueError("No web search results found.")
    return results


def _clean_duckduckgo_url(url: str) -> str:
    if not url:
        return ""
    parsed = urlparse(url)
    if parsed.netloc.endswith("duckduckgo.com") and parsed.path.startswith("/l/"):
        uddg = parse_qs(parsed.query).get("uddg", [""])[0]
        return uddg or url
    if url.startswith("//"):
        return "https:" + url
    return url


def format_search_context(results: list[dict]) -> str:
    if not results:
        return "No web search results found."
    lines = []
    for i, result in enumerate(results, 1):
        lines.append(
            f"[{i}] {result.get('title', '')}\n"
            f"URL: {result.get('url', '')}\n"
            f"Snippet: {result.get('snippet', '')}"
        )
    return "\n\n".join(lines)
