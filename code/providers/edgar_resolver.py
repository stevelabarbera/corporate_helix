#!/usr/bin/env python3
from __future__ import annotations
import json, re, urllib.request
from html import unescape
from typing import Any, Iterable
from parsers.edgar_longform_locator import locate_ma_regions

SEC_DATA = "https://data.sec.gov"
SEC_ARCHIVE = "https://www.sec.gov/Archives/edgar/data"
SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"

_SUFFIX_RE = re.compile(r"\b(corp(oration)?|inc(orporated)?|company|co|llc|l\.l\.c\.|ltd|limited|plc)\.?\s*$", re.I)

def identity_key(name: str) -> str:
    n = re.sub(r"[^a-z0-9 ]+", " ", (name or "").casefold())
    n = _SUFFIX_RE.sub("", n)
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

def _load_submissions(cik: str, user_agent: str) -> tuple[str, dict[str, Any]]:
    cik10 = str(int(cik)).zfill(10)
    return cik10, _get_json(f"{SEC_DATA}/submissions/CIK{cik10}.json", user_agent)

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
        if form not in ("8-K", "8-K/A"):
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
    cik10, submissions = _load_submissions(cik, user_agent)
    filings = _collect_recent_8k_filings(cik10, user_agent, submissions, start=start, end=end)
    return {"company": submissions.get("name"), "cik": cik10, "filings": filings}

def fetch_longform_ma_filings(
    cik: str, user_agent: str, *,
    forms: Iterable[str] = ("10-K", "10-K/A"),
    start: str = "2015-01-01", end: str = "2026-12-31",
) -> dict[str, Any]:
    cik10, submissions = _load_submissions(cik, user_agent)
    filings = _collect_recent_longform_filings(cik10, user_agent, submissions, forms=forms, start=start, end=end)
    return {"company": submissions.get("name"), "cik": cik10, "filings": filings}

def fetch_ma_filings(
    cik: str, user_agent: str, *,
    start: str = "2015-01-01", end: str = "2026-12-31",
    longform_forms: Iterable[str] = ("10-K", "10-K/A"),
) -> dict[str, Any]:
    """Fetch 8-K M&A sections plus 10-K long-form locator regions from one submissions read."""
    cik10, submissions = _load_submissions(cik, user_agent)
    filings = _collect_recent_8k_filings(cik10, user_agent, submissions, start=start, end=end)
    filings += _collect_recent_longform_filings(cik10, user_agent, submissions, forms=longform_forms, start=start, end=end)
    filings.sort(key=lambda f: (f.get("filing_date") or "", f.get("accession") or ""))
    return {"company": submissions.get("name"), "cik": cik10, "filings": filings}
