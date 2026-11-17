#!/usr/bin/env python3
"""Read-only targeted GLEIF L2 source-vs-SQLite audit.

Stream the original GLEIF RR Golden Copy ZIP file; never unpack it to disk.
Retain every raw relationship record for the specified child LEI(s), including
multiple periods and duplicates. Compare exactly what the existing importer
would keep against the local index without modifying either input.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from build_gleif_rr_index import records, _v, relationship_periods, SUPPORTED_TYPES

ROOT = Path(__file__).resolve().parents[1]
BOLTHOUSE = "254900AVSAWDJLMUWV53"
CAMPBELL = "5493007JDSMX8Z5Z1902"


def projected_fields(wrapper: dict) -> dict:
    rr = wrapper.get("RelationshipRecord", wrapper)
    rel = rr.get("Relationship") or {}
    reg = rr.get("Registration") or {}
    periods = relationship_periods(rel)
    relationship = periods.get("RELATIONSHIP_PERIOD", (None, None))
    accounting = periods.get("ACCOUNTING_PERIOD", (None, None))
    filing = periods.get("DOCUMENT_FILING_PERIOD", (None, None))
    return {
        "child_lei": _v(rel, "StartNode", "NodeID"),
        "parent_lei": _v(rel, "EndNode", "NodeID"),
        "relationship_type": _v(rel, "RelationshipType"),
        "relationship_status": _v(rel, "RelationshipStatus"),
        "relationship_start": relationship[0],
        "relationship_end": relationship[1],
        "accounting_start": accounting[0],
        "accounting_end": accounting[1],
        "document_filing_start": filing[0],
        "document_filing_end": filing[1],
        "registration_status": _v(reg, "RegistrationStatus"),
        "initial_registration_date": _v(reg, "InitialRegistrationDate"),
        "last_update_date": _v(reg, "LastUpdateDate"),
        "managing_lou": _v(reg, "ManagingLOU"),
        "validation_sources": _v(reg, "ValidationSources"),
        "validation_documents": _v(reg, "ValidationDocuments"),
        "validation_reference": _v(reg, "ValidationReference"),
    }


def inspect_source(zip_path: Path, child_leis: set[str], progress: int = 100000) -> dict:
    if not zip_path.is_file():
        raise FileNotFoundError(zip_path)
    matches = []
    scanned = 0
    for wrapper in records(str(zip_path)):
        scanned += 1
        fields = projected_fields(wrapper)
        if fields["child_lei"] in child_leis:
            matches.append({
                "source_record_ordinal": scanned,
                "projected": fields,
                "raw_record": wrapper,
            })
        if progress and scanned % progress == 0:
            print(f"  scanned {scanned:,} RR records; matched {len(matches)}", file=sys.stderr, flush=True)
    counts = Counter((
        m["projected"]["child_lei"],
        m["projected"]["parent_lei"],
        m["projected"]["relationship_type"],
    ) for m in matches if m["projected"]["relationship_type"] in SUPPORTED_TYPES)
    duplicates = [{
        "child_lei": child, "parent_lei": parent, "relationship_type": typ,
        "raw_record_count": count,
        "distinct_periods_and_updates": len({
            (m["projected"]["relationship_start"], m["projected"]["relationship_end"],
             m["projected"]["accounting_start"], m["projected"]["accounting_end"],
             m["projected"]["last_update_date"])
            for m in matches
            if (m["projected"]["child_lei"], m["projected"]["parent_lei"],
                m["projected"]["relationship_type"]) == (child, parent, typ)
        }),
    } for (child, parent, typ), count in counts.items() if count > 1]
    return {"records_scanned": scanned, "matches": matches, "duplicate_keys": duplicates}


def compare_index(rr_path: Path, matches: list[dict], child_leis: set[str]) -> dict:
    uri = f"file:{rr_path.resolve().as_posix()}?mode=ro"
    with sqlite3.connect(uri, uri=True) as conn:
        conn.row_factory = sqlite3.Row
        columns = {r[1] for r in conn.execute("PRAGMA table_info(relationships)")}
        expected = {"child_lei", "parent_lei", "relationship_type", "relationship_status"}
        if not expected.issubset(columns):
            raise RuntimeError("Missing expected L2 relationship columns")
        indexed = []
        for child in sorted(child_leis):
            indexed.extend(dict(r) for r in conn.execute(
                "SELECT * FROM relationships WHERE child_lei = ?", (child,)
            ))
    by_key = defaultdict(list)
    for m in matches:
        p = m["projected"]
        by_key[(p["child_lei"], p["parent_lei"], p["relationship_type"])].append(p)
    comparisons = []
    for row in indexed:
        key = (row["child_lei"], row["parent_lei"], row["relationship_type"])
        source_records = by_key.get(key, [])
        fields = [k for k in projected_fields({"RelationshipRecord": {}}) if k in row]
        exact_matches = [p for p in source_records if all(p.get(k) == row.get(k) for k in fields)]
        differences = {
            k: {"index": row.get(k), "source_values": list(dict.fromkeys(p.get(k) for p in source_records))}
            for k in fields if source_records and all(p.get(k) != row.get(k) for p in source_records)
        }
        comparisons.append({
            "key": {"child_lei": key[0], "parent_lei": key[1], "relationship_type": key[2]},
            "index_row": row,
            "source_records_for_key": len(source_records),
            "index_matches_complete_source_record": bool(exact_matches),
            "fields_with_no_matching_source_value": differences,
        })
    indexed_keys = {(r["child_lei"], r["parent_lei"], r["relationship_type"]) for r in indexed}
    only_in_source = [{
        "child_lei": k[0], "parent_lei": k[1], "relationship_type": k[2],
        "raw_record_count": len(v),
    } for k, v in by_key.items() if k not in indexed_keys and k[2] in SUPPORTED_TYPES]
    return {"index_rows": len(indexed), "rows": comparisons,
            "supported_keys_only_in_source": only_in_source}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--zip", type=Path, required=True, help="Original GLEIF L2 RR Golden Copy ZIP")
    ap.add_argument("--rr-index", type=Path, default=ROOT / "data/processed/gleif_rr.sqlite")
    ap.add_argument("--child-lei", action="append", default=None,
                    help="Filter child LEI; repeat for additional companies (default Bolthouse)")
    ap.add_argument("--progress", type=int, default=100000)
    ap.add_argument("--output", type=Path, default=ROOT / "data/eval_study/bolthouse_raw_rr_audit.json")
    args = ap.parse_args()
    child_leis = set(args.child_lei or [BOLTHOUSE])
    source = inspect_source(args.zip, child_leis, args.progress)
    compared = compare_index(args.rr_index, source["matches"], child_leis)
    report = {
        "schema": "corporate-helix/gleif-rr-source-audit/v1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "interpretation": "Raw file and indexed evidence comparison; NOT verified corporate ownership",
        "zip_file": str(args.zip.resolve()),
        "zip_size_bytes": args.zip.stat().st_size,
        "rr_database": str(args.rr_index.resolve()),
        "child_leis": sorted(child_leis),
        "records_scanned": source["records_scanned"],
        "raw_records_found": len(source["matches"]),
        "duplicate_keys": source["duplicate_keys"],
        "raw_matches": source["matches"],
        "index_comparison": compared,
        "inputs_modified": False,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False, default=str) + "\n",
                           encoding="utf-8")
    print(f"Scanned: {source['records_scanned']:,} raw relationships")
    print(f"Matched: {len(source['matches'])} raw child records")
    print(f"Duplicate (child, parent, type) keys: {len(source['duplicate_keys'])}")
    print(f"Index rows: {compared['index_rows']}")
    for row in compared["rows"]:
        print(f"  {row['key']['parent_lei']} | {row['key']['relationship_type']} "
              f"| source={row['source_records_for_key']} "
              f"| exact-field-match={row['index_matches_complete_source_record']}")
    print(f"Evidence report: {args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
