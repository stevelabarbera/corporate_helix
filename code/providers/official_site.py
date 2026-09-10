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
    official_declaration_match: bool = False
    declaration_reason: str | None = None
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



_SELF_IDENTIFICATION_MARKERS = (
    "registered office",
    "registered address",
    "company number",
    "registration number",
    "registered in",
    "incorporated in",
    "all rights reserved",
    "copyright",
    "website is operated by",
    "website operated by",
    "site is operated by",
    "owned and operated by",
)

_LEGAL_PATH_MARKERS = (
    "/legal",
    "/terms",
    "/privacy",
    "/imprint",
    "/company-information",
    "/company_info",
    "/corporate-information",
)

# Known third-party reference/aggregator/directory sites. These routinely
# mention a target company's exact legal name AND carry their own generic
# copyright/legal footer on the same page -- which is precisely the false
# positive the NTT stress test exposed (see CORPORATION_HELIX_CONTEXT.md
# sec 34.1-34.2): the footer belongs to the SITE, not the target entity, but
# proximity-based marker matching can't tell the difference on its own.
#
# This is intentionally a narrow, explicit exclusion list -- not an attempt
# to make the declaration heuristic itself smarter/more general. A page on
# one of these domains can still register exact_legal_name_match (useful,
# visible signal), it just can never become an official_declaration_match.
# Extend this list as new false-positive sources turn up; do not turn this
# file into a general web-classification engine.
_THIRD_PARTY_REFERENCE_DOMAINS = frozenset({
    "wikipedia.org",
    "wikidata.org",
    "wikimedia.org",
    "crunchbase.com",
    "bloomberg.com",
    "opencorporates.com",
    "zoominfo.com",
    "dnb.com",
    "linkedin.com",
    "glassdoor.com",
    "indeed.com",
    "pitchbook.com",
    "owler.com",
    "rocketreach.co",
    "sec.gov",
    "sec.report",
    "annualreports.com",
})


def _is_third_party_reference_domain(host: str) -> bool:
    host = (host or "").casefold()
    return any(host == d or host.endswith("." + d) for d in _THIRD_PARTY_REFERENCE_DOMAINS)


def _legal_name_occurrences(page: str, legal_name: str) -> list[int]:
    if not page or not legal_name:
        return []
    starts: list[int] = []
    pos = 0
    while True:
        idx = page.find(legal_name, pos)
        if idx < 0:
            break
        starts.append(idx)
        pos = idx + max(1, len(legal_name))
    return starts


def _declaration_signal(url: str, normalized_page: str, normalized_legal: str) -> tuple[bool, str | None]:
    for idx in _legal_name_occurrences(normalized_page, normalized_legal):
        left = max(0, idx - 320)
        right = min(len(normalized_page), idx + len(normalized_legal) + 320)
        window = normalized_page[left:right]

        for marker in _SELF_IDENTIFICATION_MARKERS:
            if marker in window:
                return True, f"nearby_self_identification:{marker.replace(' ', '_')}"

    path = (urlsplit(url).path or "").casefold()
    if any(marker in path for marker in _LEGAL_PATH_MARKERS):
        return False, "legal_path_without_self_identification"

    return False, "exact_name_without_self_identification"


def inspect_html(url: str, html_text: str, legal_name: str) -> OfficialSiteObservation:
    parser = _VisibleTextParser()
    parser.feed(html_text)

    host = (urlsplit(url).hostname or "").rstrip(".").lower()
    if not host:
        raise ValueError(f"URL has no hostname: {url!r}")

    normalized_page = normalize_text(parser.text)
    normalized_legal = normalize_text(legal_name)
    exact = bool(normalized_legal and normalized_legal in normalized_page)

    official_declaration = False
    declaration_reason = None
    if exact and _is_third_party_reference_domain(host):
        declaration_reason = "third_party_reference_domain"
    elif exact:
        official_declaration, declaration_reason = _declaration_signal(
            url,
            normalized_page,
            normalized_legal,
        )

    return OfficialSiteObservation(
        url=url,
        domain=host,
        title=parser.title,
        page_text=parser.text,
        matched_name=legal_name if exact else None,
        exact_legal_name_match=exact,
        match_method=(
            "normalized_exact_legal_name+self_identification"
            if official_declaration
            else ("normalized_exact_legal_name" if exact else None)
        ),
        official_declaration_match=official_declaration,
        declaration_reason=declaration_reason,
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
            official_declaration_match=result.official_declaration_match,
            declaration_reason=result.declaration_reason,
            status_code=getattr(resp, "status", None),
        )
