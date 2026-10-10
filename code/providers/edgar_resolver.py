#!/usr/bin/env python3
from __future__ import annotations
import json, re, urllib.request
from html import unescape
from typing import Any, Iterable
from parsers.edgar_longform_locator import locate_ma_regions

SEC_DATA = "https://data.sec.gov"
SEC_ARCHIVE = "https://www.sec.gov/Archives/edgar/data"
SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"

# Form families Helix retrieves. Kept as named constants (not literals buried
# in three different functions) so a new filer type is a config change, not a
# hunt through the retrieval code.
#
#   ITEMIZED_EVENT_FORMS    domestic current reports. EDGAR's submissions
#                           metadata carries Item numbers for these, so
#                           Helix can skip a download unless Item 1.01/2.01
#                           is listed.
#   FPI_EVENT_FORMS         foreign-private-issuer current reports (6-K).
#                           A 6-K has NO item numbers -- there is nothing in
#                           the metadata to pre-filter on, so these go
#                           through the same text locator the annual
#                           reports use.
#   ANNUAL_FORMS            domestic (10-K) and foreign (20-F, 40-F) annual
#                           reports, plus amendments.
#
# Added after Einride AB (Swedish, Nasdaq: ENRD, CIK 2095096) disclosed its
# July 2026 merger agreement to acquire Flipturn, Inc. in a Form 6-K: with
# only 8-K/10-K in the allowlist Helix retrieved nothing for that issuer at
# all. See ADR-EDGAR-012.
ITEMIZED_EVENT_FORMS: tuple[str, ...] = ("8-K", "8-K/A")
FPI_EVENT_FORMS: tuple[str, ...] = ("6-K", "6-K/A")
ANNUAL_FORMS: tuple[str, ...] = ("10-K", "10-K/A", "20-F", "20-F/A", "40-F", "40-F/A")
LONGFORM_FORMS: tuple[str, ...] = ANNUAL_FORMS + FPI_EVENT_FORMS

# "AB" (Swedish aktiebolag) and "publ" (as in "Einride AB (publ)", the
# public-company marker) are corporate-form words exactly like "Inc" or
# "plc": EDGAR's own registrant name is "Einride AB", so without them a plain
# "Einride" never equals the registrant name. Other European forms (GmbH,
# NV, SAS, ...) are deliberately NOT added speculatively -- each one earns a
# place the way AB did, from a real filer, because a short token stripped
# mid-string can collide with an ordinary word.
_SUFFIX_WORDS_RE = re.compile(r"\b(corp(oration)?|inc(orporated)?|company|co|llc|l\.l\.c\.|ltd|limited|plc|group|holdings?|ab|publ)\.?\b", re.I)
_LEADING_ARTICLE_RE = re.compile(r"^the\s+", re.I)
# EDGAR appends a short disambiguation tag to a registrant's own name when
# the plain name alone is ambiguous or has been reused across a corporate
# succession -- state of incorporation ("Northrop Grumman Corp /DE/") or a
# successor/predecessor marker after a merger creates a new CIK carrying
# the same trade name ("Six Flags Entertainment Corporation/NEW", confirmed
# directly against the real company_tickers.json entry for CIK 1999001,
# created at the Cedar Fair merger close on 2024-07-01). This tag is
# EDGAR's own bookkeeping, never part of the legal name a gold/study label
# would use, so strip it before any other normalization.
_EDGAR_DISAMBIGUATION_TAG_RE = re.compile(r"\s*/[A-Za-z]{1,6}\.?/?\s*$")

def identity_key(name: str) -> str:
    n = _EDGAR_DISAMBIGUATION_TAG_RE.sub("", name or "")
    n = re.sub(r"[^a-z0-9 ]+", " ", n.casefold())
    n = " ".join(n.split())
    n = _LEADING_ARTICLE_RE.sub("", n)
    # Corporate-form words get removed wherever they occur, not just at the
    # end. EDGAR's real registrant name for Service Corporation
    # International (CIK 89089) is "SERVICE CORP INTERNATIONAL" -- "Corp"
    # sits in the MIDDLE of the name, with "International" after it, so no
    # amount of end-anchored stripping can ever reach it. A trailing-only
    # strip was fine while every real case only ever stacked suffix words
    # at the tail (Colt's "Group Limited"), but that assumption doesn't
    # hold in general -- EDGAR abbreviates corporate-form words in place
    # wherever they fall in the name, not only at the end.
    n = _SUFFIX_WORDS_RE.sub("", n)
    return " ".join(n.split())

def _get_json(url: str, user_agent: str) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": user_agent})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8", "replace"))

def _get_text(url: str, user_agent: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": user_agent, "Accept-Encoding": "identity"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read().decode("utf-8", "replace")

def resolve_cik_by_name(name: str, user_agent: str, *, tickers: dict | None = None) -> str | None:
    if tickers is None:
        tickers = _get_json(SEC_TICKERS_URL, user_agent)
    target = identity_key(name)
    if not target:
        return None
    for row in tickers.values():
        if identity_key(row.get("title", "")) == target:
            return str(row["cik_str"]).zfill(10)
    return None

def strip_html(s: str) -> str:
    s = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", s)
    s = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</tr>|</li>", "\n", s)
    s = re.sub(r"(?s)<[^>]+>", " ", s)
    s = unescape(s).replace("\xa0", " ")
    s = re.sub(r"[ \t]+", " ", s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()

def item_sections(text: str) -> list[dict[str, str]]:
    marker = re.compile(r"(?m)^\s*Item\s+(\d\.\d{2})\.?\s")
    matches = list(marker.finditer(text))
    sections = []
    for i, m in enumerate(matches):
        start = m.end()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        sections.append({"item": m.group(1), "text": text[start:end].strip()})
    return sections

def _merge_older_submission_pages(
    submissions: dict[str, Any], user_agent: str, *, start: str | None, end: str | None,
) -> dict[str, Any]:
    """
    Fold EDGAR's paginated older-filing pages into the "recent" block.

    The submissions JSON only inlines roughly the most recent ~1000 filings
    (or one year, whichever is more) under filings.recent. Everything older
    lives in filings.files -- a list of {name, filingFrom, filingTo, ...}
    pointers to separate JSON pages. Reading only filings.recent therefore
    silently drops years of history for prolific filers, with no error and
    no marker in the output. Pages are fetched only when their date range
    overlaps [start, end], so a bounded study window costs only the pages
    it needs, and a company with no extra pages costs zero extra requests.
    Returns a new dict; the input is not mutated.
    """
    filings = submissions.get("filings") or {}
    pages = filings.get("files") or []
    recent = filings.get("recent") or {}
    if not pages:
        return submissions

    merged: dict[str, list[Any]] = {k: list(v) for k, v in recent.items()}
    seen = set(merged.get("accessionNumber", []))
    for page in pages:
        name = page.get("name")
        if not name:
            continue
        lo, hi = page.get("filingFrom"), page.get("filingTo")
        if start and hi and hi < start:
            continue
        if end and lo and lo > end:
            continue
        data = _get_json(f"{SEC_DATA}/submissions/{name}", user_agent)
        accessions = data.get("accessionNumber") or []
        keep = [i for i, a in enumerate(accessions) if a not in seen]
        if not keep:
            continue
        before = len(merged.get("accessionNumber", []))
        for key in set(merged) | set(data):
            col = merged.setdefault(key, [""] * before)
            src = data.get(key) or []
            # A column missing from a page is padded rather than skipped,
            # so every column stays row-aligned with accessionNumber.
            col.extend(src[i] if i < len(src) else "" for i in keep)
        seen.update(accessions[i] for i in keep)

    return {**submissions, "filings": {**filings, "recent": merged}}


def _load_submissions(
    cik: str, user_agent: str, *, start: str | None = None, end: str | None = None,
) -> tuple[str, dict[str, Any]]:
    cik10 = str(int(cik)).zfill(10)
    submissions = _get_json(f"{SEC_DATA}/submissions/CIK{cik10}.json", user_agent)
    return cik10, _merge_older_submission_pages(submissions, user_agent, start=start, end=end)

def _document_url(cik: str, accession: str, primary_doc: str) -> str:
    return f"{SEC_ARCHIVE}/{int(cik)}/{accession.replace('-', '')}/{primary_doc}"

def _rv(recent: dict[str, Any], field: str, i: int, default=None):
    vals = recent.get(field)
    if not vals or i >= len(vals):
        return default
    return vals[i]

def _collect_recent_8k_filings(cik: str, user_agent: str, submissions: dict[str, Any], *, start: str, end: str):
    recent = submissions["filings"]["recent"]
    filings = []
    for i, form in enumerate(recent.get("form", [])):
        if form not in ITEMIZED_EVENT_FORMS:
            continue
        filing_date = _rv(recent, "filingDate", i, "")
        if not (start <= filing_date <= end):
            continue
        items = _rv(recent, "items", i, "") or ""
        if not ("1.01" in items or "2.01" in items):
            continue
        accession = _rv(recent, "accessionNumber", i)
        primary_doc = _rv(recent, "primaryDocument", i)
        if not accession or not primary_doc:
            continue
        doc_url = _document_url(cik, accession, primary_doc)
        text = strip_html(_get_text(doc_url, user_agent))
        sections = [s for s in item_sections(text) if s["item"] in ("1.01", "2.01")]
        if sections:
            filings.append({
                "accession": accession, "filing_date": filing_date, "form": form, "items": items,
                "primary_document": primary_doc, "document_url": doc_url, "sections": sections,
            })
    return filings

def _collect_recent_longform_filings(cik: str, user_agent: str, submissions: dict[str, Any], *, forms: Iterable[str], start: str, end: str):
    accepted = set(forms)
    recent = submissions["filings"]["recent"]
    filings = []
    for i, form in enumerate(recent.get("form", [])):
        if form not in accepted:
            continue
        filing_date = _rv(recent, "filingDate", i, "")
        if not (start <= filing_date <= end):
            continue
        accession = _rv(recent, "accessionNumber", i)
        primary_doc = _rv(recent, "primaryDocument", i)
        if not accession or not primary_doc:
            continue
        doc_url = _document_url(cik, accession, primary_doc)
        text = strip_html(_get_text(doc_url, user_agent))
        regions = locate_ma_regions(text, form=form)
        if regions:
            filings.append({
                "accession": accession, "filing_date": filing_date, "form": form, "items": "",
                "primary_document": primary_doc, "document_url": doc_url,
                "sections": regions, "longform_locator": True,
            })
    return filings

def fetch_8k_ma_filings(cik: str, user_agent: str, *, start: str = "2015-01-01", end: str = "2026-12-31") -> dict[str, Any]:
    cik10, submissions = _load_submissions(cik, user_agent, start=start, end=end)
    filings = _collect_recent_8k_filings(cik10, user_agent, submissions, start=start, end=end)
    return {"company": submissions.get("name"), "cik": cik10, "filings": filings}

def fetch_longform_ma_filings(
    cik: str, user_agent: str, *,
    forms: Iterable[str] = LONGFORM_FORMS,
    start: str = "2015-01-01", end: str = "2026-12-31",
) -> dict[str, Any]:
    cik10, submissions = _load_submissions(cik, user_agent, start=start, end=end)
    filings = _collect_recent_longform_filings(cik10, user_agent, submissions, forms=forms, start=start, end=end)
    return {"company": submissions.get("name"), "cik": cik10, "filings": filings}

def fetch_ma_filings(
    cik: str, user_agent: str, *,
    start: str = "2015-01-01", end: str = "2026-12-31",
    longform_forms: Iterable[str] = LONGFORM_FORMS,
) -> dict[str, Any]:
    """Fetch 8-K M&A sections plus long-form locator regions (10-K, 20-F, 40-F, 6-K) in one pass.

    Older filings are folded in from EDGAR's paginated submissions pages when
    their date range overlaps [start, end]; a company without extra pages costs
    exactly one submissions request, as before.
    """
    cik10, submissions = _load_submissions(cik, user_agent, start=start, end=end)
    filings = _collect_recent_8k_filings(cik10, user_agent, submissions, start=start, end=end)
    filings += _collect_recent_longform_filings(cik10, user_agent, submissions, forms=longform_forms, start=start, end=end)
    filings.sort(key=lambda f: (f.get("filing_date") or "", f.get("accession") or ""))
    return {"company": submissions.get("name"), "cik": cik10, "filings": filings}
