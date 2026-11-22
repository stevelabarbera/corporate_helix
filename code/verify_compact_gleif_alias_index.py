#!/usr/bin/env python3
"""Independently reconcile compact alias SQLite against original Level 1 JSON.

Checks archive SHA, every alias/LEI/source ordinal, total records and counts.
Read-only verification is required before treating a complete build as usable.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sqlite3

from verify_gleif_tier1_evidence import source_records


def digest_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as source:
        for block in iter(lambda: source.read(4 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def expanded(value):
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def expected_aliases(record):
    """Independent source extraction; does not use the compact index builder."""
    entity = record.get("Entity") or {}
    groups = (
        ("Entity.OtherEntityNames.OtherEntityName",
         (entity.get("OtherEntityNames") or {}).get("OtherEntityName")),
        ("Entity.TransliteratedOtherEntityNames.TransliteratedOtherEntityName",
         (entity.get("TransliteratedOtherEntityNames") or {}).get("TransliteratedOtherEntityName")),
    )
    result = []
    for path, values in groups:
        for ordinal, raw in enumerate(expanded(values)):
            value = raw.get("$") if isinstance(raw, dict) else raw
            if not isinstance(value, str):
                raise ValueError(f"Invalid alias value: {value!r}")
            result.append((path, ordinal, value, value.strip().casefold(),
                           json.dumps(raw, ensure_ascii=False, sort_keys=True,
                                      separators=(",", ":"))))
    return result


def verify(source, database):
    source, database = Path(source).resolve(), Path(database).resolve()
    if not source.is_file() or not database.is_file():
        raise FileNotFoundError("Missing GLEIF source or compact alias DB")
    db = sqlite3.connect(f"{database.as_uri()}?mode=ro", uri=True)
    try:
        snaps = db.execute(
            "SELECT source_level,source_archive_sha256,record_count,alias_count,is_sample "
            "FROM source_snapshot"
        ).fetchall()
        if len(snaps) != 1 or snaps[0][0] != "lei":
            raise ValueError("Expected one Level 1 snapshot")
        _, expected_sha, expected_count, expected_alias_count, is_sample = snaps[0]
        actual_sha = digest_file(source)
        if actual_sha != expected_sha:
            raise ValueError("Archive checksum mismatch")
        cursor = db.execute("""
          SELECT o.source_ordinal, o.record_identifier,
                 n.source_path,n.source_ordinal,n.name,n.name_normalized,n.raw_value_json
            FROM source_observation o
            JOIN entity_name n USING(observation_id)
           ORDER BY o.source_ordinal,n.source_path,n.source_ordinal
        """)
        # Compare full record-by-record source semantics to the compact index.
        indexed = cursor.fetchone()
        scanned = 0
        aliases_seen = 0
        for scanned, record in enumerate(source_records(str(source), "lei"), 1):
            lei = record.get("LEI")
            lei = lei.get("$") if isinstance(lei, dict) else lei
            rows = sorted(expected_aliases(record))
            for row in rows:
                expected = (scanned, lei, *row)
                if indexed is None or tuple(indexed) != expected:
                    raise ValueError(f"Alias mismatch at source ordinal {scanned}: {row[:3]}")
                indexed = cursor.fetchone()
                aliases_seen += 1
            if is_sample and scanned >= expected_count:
                break
        if not scanned:
            raise ValueError("Source contains no records")
        if indexed is not None:
            raise ValueError("Extra indexed alias rows beyond source records")
        if (scanned != expected_count or aliases_seen != expected_alias_count):
            raise ValueError(
                f"Count mismatch: records {scanned}/{expected_count}; "
                f"aliases {aliases_seen}/{expected_alias_count}"
            )
        if db.execute("SELECT COUNT(*) FROM entity_name").fetchone()[0] != aliases_seen:
            raise ValueError("Alias table count mismatch")
        if db.execute("PRAGMA foreign_key_check").fetchall():
            raise ValueError("Foreign key check failed")
        return {
            "status": "PASS",
            "is_sample": bool(is_sample),
            "archive_sha256_matches": True,
            "records_verified": scanned,
            "aliases_verified": aliases_seen,
            "limitations": [
                "Complete only if built without --max-records and fully re-parsed.",
                "Alias source link is not proof of current legal ownership.",
                "Cross-snapshot LEI alignment with existing identity lookup is not established.",
            ],
        }
    finally:
        db.close()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source", required=True)
    p.add_argument("--db", required=True)
    args = p.parse_args()
    print(json.dumps(verify(args.source, args.db), indent=2))


if __name__ == "__main__":
    main()
