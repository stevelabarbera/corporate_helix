#!/usr/bin/env python3
from pathlib import Path

repo = Path.cwd()
official_path = repo / "code" / "providers" / "official_site.py"
discovery_path = repo / "code" / "domain_discovery.py"

if not official_path.is_file() or not discovery_path.is_file():
    raise SystemExit("ERROR: run this from the corporate_helix repository root")

official = official_path.read_text()

old = '''    exact_legal_name_match: bool
    match_method: str | None
    status_code: int | None = None
'''
new = '''    exact_legal_name_match: bool
    match_method: str | None
    official_declaration_match: bool = False
    declaration_reason: str | None = None
    status_code: int | None = None
'''
if old in official:
    official = official.replace(old, new, 1)
elif "official_declaration_match:" not in official:
    raise SystemExit("ERROR: could not locate OfficialSiteObservation fields")

anchor = "def inspect_html(url: str, html_text: str, legal_name: str) -> OfficialSiteObservation:\n"
helpers = r'''
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


'''
if "_SELF_IDENTIFICATION_MARKERS" not in official:
    if anchor not in official:
        raise SystemExit("ERROR: could not locate inspect_html anchor")
    official = official.replace(anchor, helpers + anchor, 1)

old = '''    normalized_page = normalize_text(parser.text)
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
'''
new = '''    normalized_page = normalize_text(parser.text)
    normalized_legal = normalize_text(legal_name)
    exact = bool(normalized_legal and normalized_legal in normalized_page)

    official_declaration = False
    declaration_reason = None
    if exact:
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
'''
if old in official:
    official = official.replace(old, new, 1)
elif "official_declaration = False" not in official:
    raise SystemExit("ERROR: could not locate inspect_html body")

old = '''            exact_legal_name_match=result.exact_legal_name_match,
            match_method=result.match_method,
            status_code=getattr(resp, "status", None),
'''
new = '''            exact_legal_name_match=result.exact_legal_name_match,
            match_method=result.match_method,
            official_declaration_match=result.official_declaration_match,
            declaration_reason=result.declaration_reason,
            status_code=getattr(resp, "status", None),
'''
if old in official:
    official = official.replace(old, new, 1)
elif "official_declaration_match=result.official_declaration_match" not in official:
    raise SystemExit("ERROR: could not locate fetch_and_inspect copy block")

official_path.write_text(official)
print("Updated code/providers/official_site.py")

discovery = discovery_path.read_text()

old = '''        if inspected.exact_legal_name_match:
            observations.append({
'''
new = '''        if inspected.official_declaration_match:
            observations.append({
'''
if old in discovery:
    discovery = discovery.replace(old, new, 1)
elif "if inspected.official_declaration_match:" not in discovery:
    raise SystemExit("ERROR: could not locate official-site promotion condition")

old = '''                    "match_method": inspected.match_method,
                    "title": inspected.title,
                    "http_status": inspected.status_code,
'''
new = '''                    "match_method": inspected.match_method,
                    "declaration_reason": inspected.declaration_reason,
                    "exact_legal_name_match": inspected.exact_legal_name_match,
                    "official_declaration_match": inspected.official_declaration_match,
                    "title": inspected.title,
                    "http_status": inspected.status_code,
'''
if old in discovery:
    discovery = discovery.replace(old, new, 1)
elif '"declaration_reason": inspected.declaration_reason' not in discovery:
    raise SystemExit("ERROR: could not locate OFFICIAL_WEBSITE raw evidence block")

discovery_path.write_text(discovery)
print("Updated code/domain_discovery.py")
