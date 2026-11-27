#!/usr/bin/env python3
"""Conservative LEI -> SEC CIK resolution for Corporate Helix.

A same-name SEC ticker lookup is a discovery heuristic, not an LEI-to-CIK
proof. An exact LEI crosswalk requires explicit recorded evidence and
must have one unambiguous CIK. Ambiguous or unverified entries never pivot.
"""
from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Callable

from providers.edgar_resolver import identity_key, resolve_cik_by_name


def normalize_cik(value: Any) -> str | None:
    raw = str(value or "").strip()
    if not raw.isdigit() or len(raw) > 10 or int(raw) == 0:
        return None
    return raw.zfill(10)


def lookup_crosswalk(lei: str | None, path: str | None) -> dict[str, Any]:
    if not lei or not path:
        return {"status": "NO_CROSSWALK_ENTRY", "cik": None}
    db = Path(path)
    if not db.is_file():
        return {"status": "CROSSWALK_FILE_NOT_FOUND", "cik": None, "path": path}
    with db.open(newline="", encoding="utf-8-sig") as handle:
        rows = list(csv.DictReader(handle))
    matches = [r for r in rows if (r.get("lei") or "").strip().upper() == lei.strip().upper()]
    verified = [
        r for r in matches
        if (r.get("verification_status") or "").strip().upper() == "VERIFIED"
        and (r.get("evidence_url") or "").strip().startswith(("https://", "http://"))
        and normalize_cik(r.get("cik"))
    ]
    ids = {normalize_cik(r["cik"]) for r in verified}
    # Any row for a LEI that conflicts with a verified CIK must be reviewed.
    all_ids = {normalize_cik(r.get("cik")) for r in matches if normalize_cik(r.get("cik"))}
    if len(ids) == 1 and all_ids == ids:
        row = verified[0]
        return {
            "status": "VERIFIED_CROSSWALK",
            "cik": next(iter(ids)),
            "identity_method": "VERIFIED_LEI_CIK_CROSSWALK",
            "identity_evidence_url": row["evidence_url"],
        }
    return {
        "status": "AMBIGUOUS_CROSSWALK" if len(all_ids) > 1 else "UNVERIFIED_CROSSWALK",
        "cik": None,
        "crosswalk_rows": len(matches),
    } if matches else {"status": "NO_CROSSWALK_ENTRY", "cik": None}


def resolve_sec_identity(
    name: str, lei: str | None, agent: str,
    *, crosswalk_path: str | None = None,
    ticker_lookup: Callable[[str, str], str | None] = resolve_cik_by_name,
) -> dict[str, Any]:
    linked = lookup_crosswalk(lei, crosswalk_path)
    if linked["status"] == "VERIFIED_CROSSWALK":
        return linked
    if linked["status"] == "AMBIGUOUS_CROSSWALK":
        return linked
    # Exact ticker-title identity is a candidate for investigation only, and
    # must never be interpreted as a verified LEI<->CIK crosswalk.
    cik = normalize_cik(ticker_lookup(name, agent))
    return {
        "status": "TICKER_EXACT_NAME_CANDIDATE" if cik else "NO_SEC_IDENTITY",
        "cik": cik,
        "identity_method": "SEC_TICKERS_EXACT_NAME",
        "crosswalk_status": linked["status"],
        "identity_verified_lei_cik": False,
    }
