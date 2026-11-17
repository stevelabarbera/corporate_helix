#!/usr/bin/env python3
"""Inspect raw GLEIF Level 2 relationship evidence without modifying the database.

Defaults to the Bolthouse Farms -> Campbell ownership discrepancy discovered
in the November 2026 real-database identity screening.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sqlite3

ROOT = Path(__file__).resolve().parents[1]
BOLTHOUSE = "254900AVSAWDJLMUWV53"
CAMPBELL = "5493007JDSMX8Z5Z1902"


def inspect(db_path: Path, child_lei: str, parent_lei: str | None = None) -> dict:
    if not db_path.is_file():
        raise FileNotFoundError(f"GLEIF relationship database not found: {db_path}")
    # Explicit SQLite read-only URI; never migrate or mutate the original DB.
    uri = f"file:{db_path.resolve().as_posix()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as conn:
        conn.row_factory = sqlite3.Row
        columns = {r[1] for r in conn.execute("PRAGMA table_info(relationships)")}
        if not {"child_lei", "parent_lei", "relationship_type", "relationship_status"}.issubset(columns):
            raise RuntimeError("This is not the expected GLEIF L2 relationships schema")
        rows = [dict(r) for r in conn.execute(
            "SELECT * FROM relationships WHERE child_lei = ? ORDER BY parent_lei, relationship_type",
            (child_lei,),
        )]
        metadata = {}
        tables = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
        if "index_metadata" in tables:
            metadata = {r[0]: r[1] for r in conn.execute("SELECT key,value FROM index_metadata")}
    return {
        "schema": "corporate-helix/gleif-relationship-evidence/v1",
        "data_kind": "RAW_L2_EVIDENCE_NOT_OWNERSHIP_VERIFICATION",
        "database": str(db_path.resolve()),
        "source_metadata": metadata,
        "child_lei": child_lei,
        "expected_parent_lei": parent_lei,
        "expected_parent_present": any(r["parent_lei"] == parent_lei for r in rows) if parent_lei else None,
        "relationship_count": len(rows),
        "relationships": rows,
        "database_modified": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rr-index", type=Path, default=ROOT / "data/processed/gleif_rr.sqlite")
    parser.add_argument("--child-lei", default=BOLTHOUSE)
    parser.add_argument("--parent-lei", default=CAMPBELL)
    parser.add_argument("--output", type=Path, default=ROOT / "data/eval_study/bolthouse_gleif_l2_evidence.json")
    args = parser.parse_args()
    report = inspect(args.rr_index, args.child_lei, args.parent_lei)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Child: {report['child_lei']}")
    print(f"Relationships found: {report['relationship_count']}")
    print(f"Target parent found: {report['expected_parent_present']}")
    for rel in report["relationships"]:
        print(
            f"  {rel.get('parent_lei')} | {rel.get('relationship_type')} "
            f"| status={rel.get('relationship_status')} "
            f"| relationship={rel.get('relationship_start')}..{rel.get('relationship_end')} "
            f"| accounting={rel.get('accounting_start')}..{rel.get('accounting_end')} "
            f"| registration={rel.get('registration_status')} "
            f"| last_update={rel.get('last_update_date')}",
            flush=True,
        )
    print(f"Detailed evidence: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
