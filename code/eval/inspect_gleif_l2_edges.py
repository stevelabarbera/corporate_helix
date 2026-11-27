#!/usr/bin/env python3
"""Read-only L2 evidence inspection for exact LEIs in SEC/GLEIF coverage JSON.

This does not create M&A events, promote parents into roots, or alter SQLite.
It deliberately exposes raw relationship dates/status: current L2 accounting
records do not reconstruct historical ownership at a past transaction date.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import date
from pathlib import Path
from typing import Any

CODE = Path(__file__).resolve().parents[1]
if str(CODE) not in sys.path:
    sys.path.insert(0, str(CODE))

from root_entity_resolver import _relationship_applies_now, _parse_relationship_date

RELATIONSHIP_TYPES = {
    "IS_DIRECTLY_CONSOLIDATED_BY", "IS_ULTIMATELY_CONSOLIDATED_BY",
}


def exact_leis(view: dict[str, Any]) -> list[str]:
    # REVIEW_REQUIRED can still have a unique exact *entity* identity.
    return sorted({str(lei).strip() for lei in (view.get("exact_seed_leis") or []) if str(lei).strip()})


def edge_view(row: dict[str, Any], as_of: str) -> dict[str, Any]:
    # The current-status test is not a historical reconstruction.
    as_of_date = date.fromisoformat(as_of)
    try:
        start = _parse_relationship_date(row.get("relationship_start"))
        end = _parse_relationship_date(row.get("relationship_end"))
        period_valid = not (start and end and start > end)
        period_error = None
    except ValueError as exc:
        period_valid = False
        period_error = str(exc)
    result = {
        "child_lei": row["child_lei"],
        "parent_lei": row["parent_lei"],
        "relationship_type": row["relationship_type"],
        "relationship_status": row.get("relationship_status"),
        "relationship_start": row.get("relationship_start"),
        "relationship_end": row.get("relationship_end"),
        "period_valid": period_valid,
        "current_snapshot_eligible_at_as_of": _relationship_applies_now(row, as_of_date),
        "historical_status_proven": False,
        "raw_record": row,
    }
    if period_error:
        result["period_error"] = period_error
    return result


def inspect(report: dict[str, Any], rr_index: str) -> dict[str, Any]:
    # Read-only SQLite URI prevents even an accidental write during audit.
    db = Path(rr_index).resolve()
    if not db.is_file():
        raise FileNotFoundError(f"GLEIF L2 database not found: {db}")
    conn = sqlite3.connect(f"{db.as_uri()}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        pairs = []
        for c in report["companies"]:
            seed = c["gleif_seed_current"]
            for event in c.get("sentinel_events", []):
                target = event["gleif_counterparty_current"]
                a_leis = exact_leis(seed)
                b_leis = exact_leis(target)
                date_of_event = event["event_date"]
                as_of = report["comparison_as_of_date"]
                date.fromisoformat(date_of_event)
                date.fromisoformat(as_of)
                # No exact match means genuinely not checked for an edge.
                edges = []
                if len(a_leis) == 1 and len(b_leis) == 1:
                    a,b=a_leis[0],b_leis[0]
                    raw = conn.execute(
                        "SELECT * FROM relationships WHERE "
                        "(child_lei=? AND parent_lei=?) OR "
                        "(child_lei=? AND parent_lei=?)",
                        (a,b,b,a)
                    ).fetchall()
                    for r in raw:
                        row=dict(r)
                        if row.get("relationship_type") in RELATIONSHIP_TYPES:
                            edges.append({
                                "current": edge_view(row, as_of),
                                "event_date": edge_view(row, date_of_event),
                            })
                    state = "EDGE_RECORDS_FOUND" if edges else "NO_DIRECT_PAIR_RECORD"
                else:
                    state = "NOT_CHECKED_NO_UNIQUE_EXACT_LEIS"
                pairs.append({
                    "company_id":c["id"],
                    "company":c["company"],
                    "counterparty":event["counterparty"],
                    "event_date":date_of_event,
                    "company_exact_leis":a_leis,
                    "counterparty_exact_leis":b_leis,
                    "edge_check":state,
                    "relationship_records":edges,
                    "sec_event_extracted":event["sec"]["event_extracted"],
                    "policy_decision":"EVIDENCE_ONLY_NOT_ACQUISITION",
                })
        return {
            "quality":"READ_ONLY_L2_PAIR_RECORD_AUDIT_NOT_HISTORICAL_MA",
            "gleif_snapshot_historical_status_reconstructed":False,
            "relationship_periods_may_be_flattened_in_current_import":True,
            "pairs":pairs,
        }
    finally:
        conn.close()


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--coverage",default="data/eval_study/sec_gleif_coverage_v1.json")
    p.add_argument("--rr-index",default="data/processed/gleif_rr.sqlite")
    p.add_argument("--out",required=True)
    a=p.parse_args(argv)
    report=inspect(json.loads(Path(a.coverage).read_text(encoding="utf-8")),a.rr_index)
    out=Path(a.out)
    out.parent.mkdir(parents=True,exist_ok=True)
    with out.open("x",encoding="utf-8") as f:
        json.dump(report,f,indent=2,ensure_ascii=False,default=str)
        f.write("\n")
    for pair in report["pairs"]:
        print(f'{pair["company_id"]}: {pair["counterparty"]} | '
              f'{pair["edge_check"]} | records={len(pair["relationship_records"])}')
    print(f"Wrote {out}")
    return 0


if __name__=="__main__":
    raise SystemExit(main())
