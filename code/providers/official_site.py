#!/usr/bin/env python3
from __future__ import annotations

"""Official-site page inspection for Corporation Helix M4.3B.

This provider does not discover ownership by itself. It inspects a supplied URL
and determines whether that page explicitly names the target legal entity.
Exact legal-name declarations are intentionally treated more strongly than
brand/name-token overlap.
"""

import html
import re
import unicodedata
import urllib.request
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urlsplit


@dataclass(frozen=True)
class OfficialSiteObservation:
    url: str
    domain: str
    title: str | None
    page_text: str
    matched_name: str | None
    exact_legal_name_match: bool
    match_method: str | None
    status_code: int | None = None


class _VisibleTextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip_depth = 0
        self._chunks: list[str] = []
        self._title_chunks: list[str] = []
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in {"script", "style", "noscript", "svg"}:
            self._skip_depth += 1
        elif tag == "title":
            self._in_title = True

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"script", "style", "noscript", "svg"}:
            if self._skip_depth:
                self._skip_depth -= 1
        elif tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        text = data.strip()
        if not text:
            return
        self._chunks.append(text)
        if self._in_title:
            self._title_chunks.append(text)

    @property
    def text(self) -> str:
        return " ".join(self._chunks)

    @property
    def title(self) -> str | None:
        value = " ".join(self._title_chunks).strip()
        return value or None


def _ascii(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    return "".join(c for c in text if not unicodedata.combining(c))


def normalize_text(text: str | None) -> str:
    if not text:
        return ""
    value = html.unescape(_ascii(text)).casefold()
    value = value.replace("&", " and ")
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def inspect_html(url: str, html_text: str, legal_name: str) -> OfficialSiteObservation:
    parser = _VisibleTextParser()
    parser.feed(html_text)

    host = (urlsplit(url).hostname or "").rstrip(".").lower()
    if not host:
        raise ValueError(f"URL has no hostname: {url!r}")

    normalized_page = normalize_text(parser.text)
    normalized_legal = normalize_text(legal_name)
    exact = bool(normalized_legal and normalized_legal in normalized_page)

    return OfficialSiteObservation(
        url=url,
        domain=host,
        title=parser.title,
        page_text=parser.text,
        matched_name=legal_name if exact else None,
        exact_legal_name_match=exact,
        match_method="normalized_exact_legal_name" if exact else None,
        status_code=None,
    )


def fetch_and_inspect(url: str, legal_name: str, timeout: int = 20) -> OfficialSiteObservation:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "CorporationHelix-M4.3B/0.1",
            "Accept": "text/html,application/xhtml+xml",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode(resp.headers.get_content_charset() or "utf-8", errors="replace")
        result = inspect_html(resp.geturl(), body, legal_name)
        return OfficialSiteObservation(
            url=result.url,
            domain=result.domain,
            title=result.title,
            page_text=result.page_text,
            matched_name=result.matched_name,
            exact_legal_name_match=result.exact_legal_name_match,
            match_method=result.match_method,
            status_code=getattr(resp, "status", None),
        )
