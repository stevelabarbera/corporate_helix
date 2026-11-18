#!/usr/bin/env python3
"""Read-only audit of GLEIF Level 2 source records versus the RR index.

Uses the same streaming ZIP record parser as build_gleif_rr_index.py. Multiple
--zip arguments permit comparisons across dated Golden Copy snapshots.
All scratch data is written into a temporary SQLite database, never to the
production RR database.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import tempfile
from collections import Counter
from pathlib import Path

from build_gleif_rr_index import SUPPORTED_TYPES, _v, records, relationship_periods

FIELDS = (
    "relationship_status", "relationship_start", "relationship_end",
    "accounting_start", "accounting_end", "document_filing_start",
    "document_filing_end", "registration_status", "last_update_date",
)
PERIOD_FIELDS = (
    "relationship_start", "relationship_end", "accounting_start",
    "accounting_end", "document_filing_start", "document_filing_end",
)
DB_FIELDS = FIELDS


def extract(wrapper):
    rr = wrapper.get("RelationshipRecord", wrapper)
    rel = rr.get("Relationship") or {}
    reg = rr.get("Registration") or {}
    rtype = _v(rel, "RelationshipType")
    if rtype not in SUPPORTED_TYPES:
        return "unsupported", None, None
    child = _v(rel, "StartNode", "NodeID")
    parent = _v(rel, "EndNode", "NodeID")
    if not child or not parent:
        return "incomplete", None, None
    periods = relationship_periods(rel)
    rp = periods.get("RELATIONSHIP_PERIOD", (None, None))
    ap = periods.get("ACCOUNTING_PERIOD", (None, None))
    fp = periods.get("DOCUMENT_FILING_PERIOD", (None, None))
    values = (
        _v(rel, "RelationshipStatus"), rp[0], rp[1],
        ap[0], ap[1], fp[0], fp[1],
        _v(reg, "RegistrationStatus"), _v(reg, "LastUpdateDate"),
    )
    return "supported", (child, parent, rtype), values


def audit(zip_paths, indexed_db=None, sample_limit=15):
    totals = Counter()
    with tempfile.TemporaryDirectory(prefix="helix-rr-audit-") as tmp:
        connection = sqlite3.connect(os.path.join(tmp, "audit.sqlite"))
        try:
            connection.execute("PRAGMA synchronous=OFF")
            connection.executescript("""
                CREATE TABLE observations (
                    child TEXT NOT NULL, parent TEXT NOT NULL, rtype TEXT NOT NULL,
                    source TEXT NOT NULL, source_ordinal INTEGER NOT NULL,
                    signature TEXT NOT NULL
                );
                CREATE INDEX observations_key ON observations(child, parent, rtype);
            """)
            for zip_path in zip_paths:
                ordinal = 0
                batch = []
                for wrapper in records(zip_path):
                    ordinal += 1
                    totals["scanned"] += 1
                    disposition, key, values = extract(wrapper)
                    totals[disposition] += 1
                    if key is None:
                        continue
                    batch.append((*key, os.path.basename(zip_path), ordinal,
                                  json.dumps(values, separators=(",", ":"))))
                    if len(batch) == 10000:
                        connection.executemany(
                            "INSERT INTO observations VALUES (?,?,?,?,?,?)", batch
                        )
                        connection.commit()
                        batch.clear()
                if batch:
                    connection.executemany(
                        "INSERT INTO observations VALUES (?,?,?,?,?,?)", batch
                    )
                    connection.commit()
                totals["source_files"] += 1
            key_stats = connection.execute("""
                SELECT child, parent, rtype, COUNT(*) n,
                       COUNT(DISTINCT signature) variants,
                       COUNT(DISTINCT source) snapshots
                FROM observations
                GROUP BY child, parent, rtype
            """).fetchall()
            duplicate_keys = [r for r in key_stats if r[3] > 1]
            differing_keys = [r for r in duplicate_keys if r[4] > 1]
            examples = []
            for child, parent, rtype, count, variants, snapshots in differing_keys[:sample_limit]:
                rows = connection.execute("""
                    SELECT source, source_ordinal, signature
                    FROM observations
                    WHERE child=? AND parent=? AND rtype=?
                    ORDER BY source, source_ordinal
                    LIMIT 6
                """, (child, parent, rtype)).fetchall()
                examples.append({
                    "child_lei": child, "parent_lei": parent,
                    "relationship_type": rtype,
                    "source_records": count, "distinct_versions": variants,
                    "snapshots": snapshots,
                    "observations": [
                        {"source": source, "source_record_number": number,
                         **dict(zip(FIELDS, json.loads(signature)))}
                        for source, number, signature in rows
                    ],
                    "observations_truncated": count > len(rows),
                })
            result = {
                "method": "same parser and supported relationship types as build_gleif_rr_index.py",
                "source_files": [str(Path(p).resolve()) for p in zip_paths],
                "counts": {
                    **dict(totals),
                    "unique_relationship_keys": len(key_stats),
                    "duplicate_relationship_keys": len(duplicate_keys),
                    "duplicate_source_records_beyond_one_per_key":
                        sum(r[3] - 1 for r in duplicate_keys),
                    "keys_with_different_status_or_period_metadata": len(differing_keys),
                    "keys_with_identical_repeated_metadata":
                        len(duplicate_keys) - len(differing_keys),
                },
                "interpretation": (
                    "The current unique (child,parent,type) index permits only "
                    "one row per key. Differing versions for a key cannot coexist "
                    "in that table; this audit does not prove which source version "
                    "was originally loaded or whether a prior snapshot survived."
                ),
                "examples": examples,
            }
            if indexed_db:
                uri = Path(indexed_db).resolve().as_uri() + "?mode=ro"
                existing = sqlite3.connect(uri, uri=True)
                try:
                    stored = existing.execute("SELECT COUNT(*) FROM relationships").fetchone()[0]
                    stored_keys = existing.execute("""
                        SELECT COUNT(*) FROM (
                            SELECT child_lei, parent_lei, relationship_type
                            FROM relationships
                            GROUP BY child_lei, parent_lei, relationship_type
                        )
                    """).fetchone()[0]
                    result["existing_index"] = {
                        "path": str(Path(indexed_db).resolve()),
                        "rows": stored, "unique_relationship_keys": stored_keys,
                        "note": "Index counts are descriptive; source ZIPs may differ from the ZIP used to build this index.",
                    }
                finally:
                    existing.close()
            return result
        finally:
            connection.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--zip", dest="zips", action="append", required=True,
                        help="GLEIF Level 2 Golden Copy ZIP; repeat for historical snapshots")
    parser.add_argument("--indexed-db", help="Existing GLEIF RR SQLite file (read-only)")
    parser.add_argument("--sample-limit", type=int, default=15)
    parser.add_argument("--out", help="Optional JSON report path; stdout always prints report")
    args = parser.parse_args()
    if args.sample_limit < 0:
        parser.error("--sample-limit must be >= 0")
    for p in args.zips:
        if not Path(p).is_file():
            parser.error(f"ZIP not found: {p}")
    if args.indexed_db and not Path(args.indexed_db).is_file():
        parser.error(f"index database not found: {args.indexed_db}")
    report = audit(args.zips, args.indexed_db, args.sample_limit)
    payload = json.dumps(report, indent=2)
    if args.out:
        target = Path(args.out)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(payload + "\n", encoding="utf-8")
    print(payload)


if __name__ == "__main__":
    main()
