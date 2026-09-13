#!/usr/bin/env python3
"""
General-purpose SEC EDGAR company resolution and 8-K M&A filing fetch.

Network acquisition is intentionally separate from parsing so provider tests
can inject fixture-backed filing data.
"""
from __future__ import annotations

import json
import re
import urllib.request
from html import unescape
from typing import Any

SEC_DATA = "https://data.sec.gov"
SEC_ARCHIVE = "https://www.sec.gov/Archives/edgar/data"
SEC_TICKERS_URL = "https://www.sec.gov/files/company_tickers.json"

_SUFFIX_RE = re.compile(
    r"\b(corp(oration)?|inc(orporated)?|company|co|llc|l\.l\.c\.|ltd|limited|plc)\.?\s*$",
    re.I,
)


def identity_key(name: str) -> str:
    """Name-comparison key only; not a canonical legal-entity identifier."""
    n = re.sub(r"[^a-z0-9 ]+", " ", (name or "").casefold())
    n = _SUFFIX_RE.sub("", n)
    return " ".join(n.split())


def _get_json(url: str, user_agent: str) -> Any:
    req = urllib.request.Request(url, headers={"User-Agent": user_agent})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8", "replace"))


def _get_text(url: str, user_agent: str) -> str:
    req = urllib.request.Request(
        url, headers={"User-Agent": user_agent, "Accept-Encoding": "identity"}
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        return resp.read().decode("utf-8", "replace")


def resolve_cik_by_name(
    name: str, user_agent: str, *, tickers: dict | None = None
) -> str | None:
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


def fetch_8k_ma_filings(
    cik: str, user_agent: str, *, start: str = "2015-01-01", end: str = "2026-12-31"
) -> dict[str, Any]:
    """
    Fetch recent 8-K/8-K-A Item 1.01/2.01 filings.

    Historical limitation preserved/documented:
    this currently reads submissions["filings"]["recent"] only. The start/end
    arguments therefore do NOT guarantee exhaustive historical coverage for
    prolific filers whose older submissions live in SEC history files.
    Long-form and historical retrieval are separate follow-up work.
    """
    cik10 = str(int(cik)).zfill(10)
    submissions = _get_json(f"{SEC_DATA}/submissions/CIK{cik10}.json", user_agent)
    company_name = submissions.get("name")
    recent = submissions["filings"]["recent"]

    filings = []
    for i, form in enumerate(recent["form"]):
        if form not in ("8-K", "8-K/A"):
            continue
        filing_date = recent["filingDate"][i]
        if not (start <= filing_date <= end):
            continue
        items = (recent.get("items") or [""] * len(recent["form"]))[i] or ""
        if not ("1.01" in items or "2.01" in items):
            continue

        accession = recent["accessionNumber"][i]
        primary_doc = recent["primaryDocument"][i]
        accession_nodash = accession.replace("-", "")
        doc_url = f"{SEC_ARCHIVE}/{int(cik)}/{accession_nodash}/{primary_doc}"

        html = _get_text(doc_url, user_agent)
        text = strip_html(html)
        sections = [s for s in item_sections(text) if s["item"] in ("1.01", "2.01")]
        if not sections:
            continue

        filings.append({
            "accession": accession,
            "filing_date": filing_date,
            "form": form,
            "items": items,
            # Added in the trust/provenance hardening pass. These fields make
            # an emitted Helix evidence record traceable back to its SEC source.
            "primary_document": primary_doc,
            "document_url": doc_url,
            "sections": sections,
        })

    return {"company": company_name, "cik": cik10, "filings": filings}
