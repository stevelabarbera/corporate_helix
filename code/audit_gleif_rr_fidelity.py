#!/usr/bin/env python3
"""Read-only field-fidelity audit: GLEIF RR Golden Copy versus SQLite.

Uses the same record stream as the production importer, then independently
maps each source record to the importer column contract. It does NOT rebuild
or mutate the target index, nor does it certify the source parser itself.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sqlite3
from urllib.parse import quote

from build_gleif_rr_index import SUPPORTED_TYPES, _v, records, relationship_periods

KEYS = ("child_lei", "parent_lei", "relationship_type")
FIELDS = (
    "relationship_status", "relationship_start", "relationship_end",
    "accounting_start", "accounting_end", "document_filing_start",
    "document_filing_end", "registration_status", "initial_registration_date",
    "last_update_date", "managing_lou", "validation_sources",
    "validation_documents", "validation_reference",
)
ALL_COLUMNS = KEYS + FIELDS
PERIOD_TYPES = ("RELATIONSHIP_PERIOD", "ACCOUNTING_PERIOD", "DOCUMENT_FILING_PERIOD")


def map_record(wrapper):
    rr = wrapper.get("RelationshipRecord", wrapper)
    rel = rr.get("Relationship") or {}
    reg = rr.get("Registration") or {}
    rtype = _v(rel, "RelationshipType")
    if rtype not in SUPPORTED_TYPES:
        return "unsupported", rtype or "<missing>", None, Counter()
    child = _v(rel, "StartNode", "NodeID")
    parent = _v(rel, "EndNode", "NodeID")
    if not child or not parent:
        return "incomplete", rtype, None, Counter()
    raw_periods = (rel.get("RelationshipPeriods") or {}).get("RelationshipPeriod") or []
    if isinstance(raw_periods, dict):
        raw_periods = [raw_periods]
    period_counts = Counter(
        _v(p, "PeriodType") for p in raw_periods if isinstance(p, dict)
    )
    periods = relationship_periods(rel)
    rp = periods.get("RELATIONSHIP_PERIOD", (None, None))
    ap = periods.get("ACCOUNTING_PERIOD", (None, None))
    fp = periods.get("DOCUMENT_FILING_PERIOD", (None, None))
    row = (
        child, parent, rtype, _v(rel, "RelationshipStatus"),
        rp[0], rp[1], ap[0], ap[1], fp[0], fp[1],
        _v(reg, "RegistrationStatus"), _v(reg, "InitialRegistrationDate"),
        _v(reg, "LastUpdateDate"), _v(reg, "ManagingLOU"),
        _v(reg, "ValidationSources"), _v(reg, "ValidationDocuments"),
        _v(reg, "ValidationReference"),
    )
    return "supported", rtype, row, period_counts


def inspect(source_zip: str, index_db: str, sample_limit: int = 12):
    if sample_limit < 0:
        raise ValueError("sample_limit must be nonnegative")
    uri = Path(index_db).resolve().as_uri() + "?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    try:
        columns = {r["name"] for r in conn.execute("PRAGMA table_info(relationships)")}
        missing = set(ALL_COLUMNS) - columns
        if missing:
            raise ValueError("Index lacks required columns: " + ", ".join(sorted(missing)))
        sql = ("SELECT " + ", ".join(ALL_COLUMNS)
               + " FROM relationships WHERE child_lei=? AND parent_lei=? AND relationship_type=?")
        totals = Counter()
        mismatch_fields = Counter()
        source_types = Counter()
        repeated_periods = Counter()
        samples = []
        source_keys = set()
        # 260k 3-field keys is manageable; detect missing index rows separately below.
        for ordinal, wrapper in enumerate(records(source_zip), 1):
            totals["source_records"] += 1
            kind, rtype, expected, pcounts = map_record(wrapper)
            source_types[rtype] += 1
            totals[kind] += 1
            if expected is None:
                continue
            key = tuple(expected[:3])
            source_keys.add(key)
            for kind_name, count in pcounts.items():
                if count > 1:
                    repeated_periods[kind_name or "<missing>"] += 1
            stored = conn.execute(sql, key).fetchone()
            if stored is None:
                totals["missing_in_index"] += 1
                if len(samples) < sample_limit:
                    samples.append({"record_number": ordinal, "key": key, "problem": "missing_index_row"})
                continue
            failures = {}
            for col, value in zip(ALL_COLUMNS, expected):
                if stored[col] != value:
                    mismatch_fields[col] += 1
                    if len(samples) < sample_limit:
                        failures[col] = {"source": value, "index": stored[col]}
            if failures:
                totals["rows_with_field_mismatch"] += 1
                if len(samples) < sample_limit:
                    samples.append({"record_number": ordinal, "key": key, "mismatches": failures})
            else:
                totals["rows_matching_all_compared_fields"] += 1
        totals["unique_source_keys"] = len(source_keys)
        totals["index_rows"] = conn.execute("SELECT COUNT(*) FROM relationships").fetchone()[0]
        totals["source_key_duplicates"] = totals["supported"] - len(source_keys)
        # A count equality doesn't prove every index key appears in the source.
        # For full key-set fidelity, compare against all index keys.
        index_keys = {
            tuple(row) for row in conn.execute(
                "SELECT child_lei, parent_lei, relationship_type FROM relationships"
            )
        }
        totals["index_keys_absent_from_source"] = len(index_keys - source_keys)
        metadata = {}
        has_meta = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE name='index_metadata' AND type='table'"
        ).fetchone()
        if has_meta:
            metadata = dict(conn.execute("SELECT key,value FROM index_metadata"))
        return {
            "source_zip": str(Path(source_zip).resolve()),
            "index_db": str(Path(index_db).resolve()),
            "index_metadata": {
                key: metadata.get(key) for key in (
                    "source_file", "build_status", "records_scanned",
                    "records_indexed_supported", "build_completed_unix"
                )
            },
            "source_filename_matches_index_metadata": (
                Path(metadata["source_file"]).name == Path(source_zip).name
                if metadata.get("source_file") else None
            ),
            "counts": dict(totals),
            "source_relationship_types": dict(source_types.most_common()),
            "fields_with_mismatches": dict(mismatch_fields.most_common()),
            "records_with_repeated_period_type": dict(repeated_periods),
            "examples": samples,
            "limitations": [
                "Uses production ZIP record parser; cannot independently prove it found every JSON record.",
                "Compares importer-selected columns, not every original provider attribute.",
                "Does not validate semantic correctness or legal ownership.",
                "Source/index mismatch can reflect different snapshot dates; check source_filename_matches_index_metadata.",
            ],
        }
    finally:
        conn.close()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--zip", required=True, help="Original GLEIF RR JSON ZIP")
    ap.add_argument("--indexed-db", required=True, help="Existing SQLite RR index (read-only)")
    ap.add_argument("--sample-limit", type=int, default=12)
    ap.add_argument("--out", help="Optional JSON report path")
    args = ap.parse_args()
    for value in (args.zip, args.indexed_db):
        if not Path(value).is_file():
            ap.error(f"File not found: {value}")
    report = inspect(args.zip, args.indexed_db, args.sample_limit)
    body = json.dumps(report, indent=2, ensure_ascii=False)
    if args.out:
        target = Path(args.out)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body + "\n", encoding="utf-8")
    print(body)


if __name__ == "__main__":
    main()
