#!/usr/bin/env python3
"""
Per-company EDGAR coverage manifest (docs/BACKLOG.md, "Foundation").

Metadata only: this reads the submissions JSON Helix already reads and records,
for EVERY filing in the window, what the retrieval layer does with it and why.
Nothing is downloaded. The point is to turn "we discovered by hand that Helix
never looked at 6-Ks" into a report that says so on the first run for a new
company.

The decision logic lives in `classify_filing`, which mirrors the collectors in
edgar_resolver.py (8-K Item 1.01/2.01 gate; long-form locator forms). A parity
test (tests/test_edgar_coverage.py) fails if the two ever drift apart.
"""
from __future__ import annotations

from collections import Counter
from typing import Any

from providers.edgar_resolver import ITEMIZED_EVENT_FORMS, LONGFORM_FORMS, _rv

# Dispositions
FETCHED_ITEM_GATED = "fetched_item_gated"        # 8-K with Item 1.01/2.01
FETCHED_LOCATOR = "fetched_via_locator"          # 10-K/20-F/40-F/6-K family
SKIP_ITEM_GATE = "skipped_item_gate"             # 8-K, items present, none of 1.01/2.01
SKIP_NO_ITEMS = "skipped_no_item_metadata"       # 8-K with EMPTY items: cannot be gated, silently dropped today
SKIP_UNSUPPORTED_DEAL = "skipped_unsupported_deal_relevant"
SKIP_UNSUPPORTED_OTHER = "skipped_unsupported_other"
OUT_OF_WINDOW = "out_of_window"

FETCHED = {FETCHED_ITEM_GATED, FETCHED_LOCATOR}

# Forms Helix does not retrieve but that routinely carry deal information.
# Deliberately a curated list, not "everything else": the report should be
# actionable. Extend it when a miss teaches us a new family.
DEAL_RELEVANT_UNSUPPORTED = frozenset({
    "10-Q", "10-Q/A", "10-QT", "10-KT", "10-KT/A", "10-K405",
    "S-4", "S-4/A", "F-4", "F-4/A", "425", "DEFM14A", "PREM14A", "DEFA14A",
    "SC TO-T", "SC TO-T/A", "SC TO-I", "SC 14D9", "SC 14D9/A", "SC 13E3",
})


def classify_filing(form: str, items: str) -> tuple[str, str]:
    """(disposition, reason) for one in-window filing. Mirrors the collectors."""
    if form in ITEMIZED_EVENT_FORMS:
        if not (items or "").strip():
            return SKIP_NO_ITEMS, "8-K has no item metadata, so the Item 1.01/2.01 gate cannot pass it"
        if "1.01" in items or "2.01" in items:
            return FETCHED_ITEM_GATED, "8-K reporting Item 1.01 or 2.01"
        return SKIP_ITEM_GATE, f"8-K items {items!r} include neither 1.01 nor 2.01"
    if form in LONGFORM_FORMS:
        return FETCHED_LOCATOR, "long-form form; M&A regions found by keyword locator"
    if form in DEAL_RELEVANT_UNSUPPORTED:
        return SKIP_UNSUPPORTED_DEAL, f"{form} can carry deal information but is not retrieved"
    return SKIP_UNSUPPORTED_OTHER, f"{form} is not retrieved"


def summarize_pages(raw_submissions: dict[str, Any], *, start: str, end: str) -> list[dict[str, Any]]:
    """Paginated older-filing pages (filings.files) and whether the window needs them."""
    out = []
    for page in raw_submissions.get("filings", {}).get("files", []) or []:
        lo, hi = page.get("filingFrom", ""), page.get("filingTo", "")
        out.append({
            "name": page.get("name"), "filingFrom": lo, "filingTo": hi,
            "overlaps_window": bool(lo and hi and not (hi < start or lo > end)),
        })
    return out


def build_manifest(
    submissions: dict[str, Any], *, start: str, end: str,
    pages: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """`submissions` should already have older pages merged (edgar_resolver._load_submissions)."""
    recent = submissions["filings"]["recent"]
    rows = []
    for i, form in enumerate(recent.get("form", [])):
        date = _rv(recent, "filingDate", i, "") or ""
        items = _rv(recent, "items", i, "") or ""
        if not (start <= date <= end):
            disp, reason = OUT_OF_WINDOW, f"filed {date or '?'}, outside {start}..{end}"
        else:
            disp, reason = classify_filing(form, items)
        rows.append({
            "accession": _rv(recent, "accessionNumber", i), "form": form, "filing_date": date,
            "items": items, "primary_document": _rv(recent, "primaryDocument", i),
            "disposition": disp, "reason": reason,
        })

    in_window = [r for r in rows if r["disposition"] != OUT_OF_WINDOW]
    by_disp = Counter(r["disposition"] for r in in_window)
    unsupported = Counter(r["form"] for r in in_window if r["disposition"] == SKIP_UNSUPPORTED_DEAL)
    fetched = sum(by_disp[d] for d in FETCHED)

    flags = []
    if in_window and fetched == 0:
        flags.append(f"NOTHING RETRIEVED: {len(in_window)} filings in window, none eligible for retrieval "
                     f"(forms present: {sorted({r['form'] for r in in_window})})")
    if by_disp[SKIP_NO_ITEMS]:
        flags.append(f"{by_disp[SKIP_NO_ITEMS]} 8-K filing(s) have no item metadata and are silently dropped")
    if unsupported:
        flags.append("deal-relevant forms present but not retrieved: "
                     + ", ".join(f"{f} x{n}" for f, n in sorted(unsupported.items())))
    needed = [p for p in (pages or []) if p["overlaps_window"]]
    if needed:
        flags.append(f"{len(needed)} older submissions page(s) overlap the window "
                     f"(merged only if the caller used _load_submissions with start/end)")

    return {
        "company": submissions.get("name"), "cik": submissions.get("cik"),
        "window": {"start": start, "end": end},
        "totals": {"filings_total": len(rows), "in_window": len(in_window), "retrievable": fetched},
        "by_disposition": dict(by_disp),
        "by_form": dict(Counter(r["form"] for r in in_window)),
        "pages": pages or [], "flags": flags, "rows": rows,
    }


def render_markdown(m: dict[str, Any]) -> str:
    t = m["totals"]
    lines = [
        f"# EDGAR coverage: {m['company']} (CIK {m['cik']})",
        f"Window {m['window']['start']} .. {m['window']['end']}: "
        f"{t['in_window']} filings, {t['retrievable']} eligible for retrieval.", "",
        "## Flags", *([f"- {f}" for f in m["flags"]] or ["- none"]), "",
        "## Disposition", *[f"- {k}: {v}" for k, v in sorted(m["by_disposition"].items())], "",
        "## Forms in window", *[f"- {k}: {v}" for k, v in sorted(m["by_form"].items())],
    ]
    return "\n".join(lines) + "\n"
