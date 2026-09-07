#!/usr/bin/env python3
from __future__ import annotations

"""Public-web search adapter for M4.3B candidate discovery.

Search results are candidate provenance only; they are never treated as
ownership evidence.

Provider order:
1. DuckDuckGo HTML no-JS endpoint via POST.
2. Bing RSS fallback.

The adapter is deliberately standard-library only and raises a provider error
when every backend fails or returns an unusable/empty response. That prevents a
blocked search page from being mistaken for a legitimate "zero candidates"
result.
"""

from dataclasses import dataclass
from html.parser import HTMLParser
import html
import urllib.parse
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET


@dataclass(frozen=True)
class SearchResult:
    url: str
    title: str


class SearchProviderError(RuntimeError):
    pass


class _DuckDuckGoResultsParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._href: str | None = None
        self._title_parts: list[str] = []
        self.results: list[SearchResult] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        attr = {k.lower(): v for k, v in attrs if k}
        classes = set((attr.get("class") or "").split())
        if "result__a" in classes and attr.get("href"):
            self._href = str(attr["href"])
            self._title_parts = []

    def handle_data(self, data: str) -> None:
        if self._href is not None:
            value = data.strip()
            if value:
                self._title_parts.append(value)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() != "a" or self._href is None:
            return
        url = _unwrap_duckduckgo_url(self._href)
        title = html.unescape(" ".join(self._title_parts)).strip()
        if url and title:
            self.results.append(SearchResult(url=url, title=title))
        self._href = None
        self._title_parts = []


def _unwrap_duckduckgo_url(value: str) -> str | None:
    value = html.unescape(value).strip()
    if not value:
        return None

    if value.startswith("//"):
        value = "https:" + value

    parsed = urllib.parse.urlsplit(value)
    if parsed.path.startswith("/l/"):
        target = urllib.parse.parse_qs(parsed.query).get("uddg", [None])[0]
        if target:
            value = urllib.parse.unquote(target)
            parsed = urllib.parse.urlsplit(value)

    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return None

    host = parsed.hostname.lower().rstrip(".")
    if host.endswith("duckduckgo.com"):
        return None
    return value


def parse_search_html(html_text: str, limit: int = 5) -> list[SearchResult]:
    parser = _DuckDuckGoResultsParser()
    parser.feed(html_text)

    results: list[SearchResult] = []
    seen: set[str] = set()
    for result in parser.results:
        if result.url in seen:
            continue
        seen.add(result.url)
        results.append(result)
        if len(results) >= max(1, limit):
            break
    return results


def parse_bing_rss(xml_text: str, limit: int = 5) -> list[SearchResult]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise SearchProviderError(f"Bing RSS returned invalid XML: {exc}") from exc

    results: list[SearchResult] = []
    seen: set[str] = set()

    for item in root.findall(".//item"):
        title = (item.findtext("title") or "").strip()
        url = (item.findtext("link") or "").strip()
        if not title or not url:
            continue
        parsed = urllib.parse.urlsplit(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            continue
        if url in seen:
            continue
        seen.add(url)
        results.append(SearchResult(url=url, title=title))
        if len(results) >= max(1, limit):
            break

    return results


def _browser_headers() -> dict[str, str]:
    return {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/151.0.0.0 Safari/537.36"
        ),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }


def _duckduckgo_search(query: str, *, limit: int, timeout: int) -> list[SearchResult]:
    url = "https://html.duckduckgo.com/html/"
    body = urllib.parse.urlencode({"q": query, "b": ""}).encode("utf-8")
    headers = _browser_headers()
    headers.update({
        "Content-Type": "application/x-www-form-urlencoded",
        "Origin": "https://html.duckduckgo.com",
        "Referer": "https://html.duckduckgo.com/",
    })
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")

    with urllib.request.urlopen(req, timeout=timeout) as resp:
        text = resp.read().decode(resp.headers.get_content_charset() or "utf-8", errors="replace")

    lowered = text.lower()
    if any(marker in lowered for marker in (
        "anomaly-modal",
        "challenge-form",
        "captcha",
        "bots use duckduckgo too",
    )):
        raise SearchProviderError("DuckDuckGo returned a bot/challenge page")

    results = parse_search_html(text, limit=limit)
    if not results:
        raise SearchProviderError(
            f"DuckDuckGo returned HTTP content but no parseable results (body_length={len(text)})"
        )
    return results


def _bing_rss_search(query: str, *, limit: int, timeout: int) -> list[SearchResult]:
    params = urllib.parse.urlencode({"q": query, "format": "rss"})
    url = "https://www.bing.com/search?" + params
    headers = _browser_headers()
    headers["Accept"] = "application/rss+xml,application/xml,text/xml;q=0.9,*/*;q=0.8"
    req = urllib.request.Request(url, headers=headers)

    with urllib.request.urlopen(req, timeout=timeout) as resp:
        text = resp.read().decode(resp.headers.get_content_charset() or "utf-8", errors="replace")

    results = parse_bing_rss(text, limit=limit)
    if not results:
        raise SearchProviderError(
            f"Bing RSS returned HTTP content but no parseable results (body_length={len(text)})"
        )
    return results


def search_official_site_candidates(
    legal_name: str,
    *,
    limit: int = 5,
    timeout: int = 20,
) -> tuple[str, list[SearchResult]]:
    query = f'"{legal_name}" official website'
    errors: list[str] = []

    for provider_name, fn in (
        ("duckduckgo_html", _duckduckgo_search),
        ("bing_rss", _bing_rss_search),
    ):
        try:
            results = fn(query, limit=limit, timeout=timeout)
            return query, results
        except (SearchProviderError, urllib.error.URLError, TimeoutError, OSError) as exc:
            errors.append(f"{provider_name}: {type(exc).__name__}: {exc}")

    raise SearchProviderError("All search providers failed: " + " | ".join(errors))
