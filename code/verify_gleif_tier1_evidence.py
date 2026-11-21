#!/usr/bin/env python3
"""Independently verify staged GLEIF records against original JSON ZIP/file.

Uses ijson's structural parser for BOTH levels (not RR's legacy line parser).
Checks selected source records, their exact parsed JSON value structure, and
every Tier-1 child element in original array order. Read-only, exit nonzero
on differences. This verifies parser-level fidelity, not byte-for-byte JSON.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sqlite3
import zlib

from audit_gleif_cardinality import source_stream


def source_records(source, level="lei"):
    """Read records using source structure, independently of the line-based RR importer.

    The official RR Golden Copy places RelationshipRecord entries under a
    container rather than necessarily a Level-1-style records array. Locate
    the actual path by structural events and fail closed if none exists.
    """
    import ijson
    if level == "lei":
        path, wrap = "records.item", False
    elif level == "rr":
        with source_stream(source) as reader:
            path, wrap = None, False
            for prefix, event, value in ijson.parse(reader):
                if event == "map_key" and value == "RelationshipRecord":
                    if prefix.endswith(".item"):
                        # Each records.item is already a wrapper object.
                        path, wrap = prefix, False
                    else:
                        # A container holds RelationshipRecord entries.
                        # The next structural event distinguishes array vs object.
                        path = prefix + ".RelationshipRecord"
                        wrap = True
                    break
            if path is None:
                raise ValueError("RR source lacks a RelationshipRecord key")
            if wrap:
                with source_stream(source) as inner:
                    found = False
                    for pre, evt, _ in ijson.parse(inner):
                        if pre == path and evt in ("start_array", "start_map"):
                            if evt != "start_array":
                                raise ValueError(
                                    f"RR RelationshipRecord container at {path} is not an array"
                                )
                            path += ".item"
                            found = True
                            break
                    if not found:
                        raise ValueError("RR RelationshipRecord array not found")
    else:
        raise ValueError(f"Unknown GLEIF level: {level}")

    with source_stream(source) as reader:
        count = 0
        for obj in ijson.items(reader, path):
            count += 1
            if not isinstance(obj, dict):
                raise ValueError("GLEIF record must be a JSON object")
            yield {"RelationshipRecord": obj} if wrap else obj
        if not count:
            raise ValueError(f"No {level.upper()} records found at detected JSON path: {path}")


def jdump(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)


def sequence(value):
    return value if isinstance(value, list) else ([] if value is None else [value])


def scalar(value):
    return value.get("$") if isinstance(value, dict) else value


def normalized_name(value):
    return value.strip().casefold() if isinstance(value, str) else None


def raw_children(level, record):
    """Independent source-path extraction, without invoking the stage writer."""
    if level == "lei":
        entity = record.get("Entity") or {}
        other = entity.get("OtherEntityNames") or {}
        translated = entity.get("TransliteratedOtherEntityNames") or {}
        names = []
        for path, elements in [
            ("Entity.LegalName", sequence(entity.get("LegalName"))),
            ("Entity.OtherEntityNames.OtherEntityName",
             sequence(other.get("OtherEntityName"))),
            ("Entity.TransliteratedOtherEntityNames.TransliteratedOtherEntityName",
             sequence(translated.get("TransliteratedOtherEntityName"))),
        ]:
            names.extend((path, n, scalar(value), normalized_name(scalar(value)), jdump(value))
                         for n, value in enumerate(elements))
        return {
            "entity_name": names,
            "entity_event": [(n, jdump(value)) for n, value in enumerate(
                sequence((entity.get("LegalEntityEvents") or {}).get("LegalEntityEvent")))],
            "entity_successor": [(n, jdump(value)) for n, value in enumerate(
                sequence(entity.get("SuccessorEntity")))],
        }
    rr = record.get("RelationshipRecord", record)
    rel = rr.get("Relationship") or {}
    return {
        "relationship_period": [
            (n, scalar(value.get("PeriodType")),
             scalar(value.get("StartDate")), scalar(value.get("EndDate")),
             jdump(value))
            for n, value in enumerate(
                sequence((rel.get("RelationshipPeriods") or {}).get("RelationshipPeriod")))
        ],
        "relationship_qualifier": [(n, jdump(value)) for n, value in enumerate(
            sequence((rel.get("RelationshipQualifiers") or {}).get("RelationshipQualifier")))],
    }


def file_sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as raw:
        for chunk in iter(lambda: raw.read(4 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def verify(source, database):
    source = Path(source).resolve()
    conn = sqlite3.connect(f"{Path(database).resolve().as_uri()}?mode=ro", uri=True)
    try:
        snapshots = conn.execute(
            "SELECT source_level, source_archive_sha256, record_count, is_sample FROM source_snapshot"
        ).fetchall()
        if len(snapshots) != 1:
            raise RuntimeError("Expected exactly one source snapshot")
        level, archive_sha, expected_count, is_sample = snapshots[0]
        if level not in ("lei", "rr"):
            raise RuntimeError("Invalid stage source level")
        if file_sha256(source) != archive_sha:
            raise RuntimeError("Source archive SHA-256 does not match staged provenance")
        rows = conn.execute(
            "SELECT source_ordinal, observation_id, source_record_sha256, source_record_zlib "
            "FROM source_observation ORDER BY source_ordinal"
        ).fetchall()
        if len(rows) != expected_count or not rows:
            raise RuntimeError("Staged observation count mismatch/empty database")
        if len({r[0] for r in rows}) != len(rows):
            raise RuntimeError("Duplicate source ordinal")
        positions = {r[0]: r for r in rows}
        errors = []
        found = set()
        counts = Counter()
        last_ordinal = max(positions)
        for ordinal, raw in enumerate(source_records(str(source), level), 1):
            if ordinal not in positions:
                if is_sample and ordinal >= last_ordinal:
                    break
                continue
            row = positions[ordinal]
            found.add(ordinal)
            _, observation_id, expected_hash, stored_blob = row
            try:
                stored_bytes = zlib.decompress(stored_blob)
                stored_obj = json.loads(stored_bytes)
                calculated_hash = hashlib.sha256(stored_bytes).hexdigest()
                # Both content and parsed values must match independently parsed source.
                if calculated_hash != expected_hash or stored_obj != raw:
                    errors.append({"ordinal": ordinal, "kind": "SOURCE_RECORD_MISMATCH"})
                # This additionally flags type changes from canonical serialization.
                if jdump(raw).encode("utf-8") != stored_bytes:
                    errors.append({"ordinal": ordinal, "kind": "CANONICAL_REPRESENTATION_MISMATCH"})
                for table, wanted in raw_children(level, raw).items():
                    if table == "entity_name":
                        actual = conn.execute(
                            "SELECT source_path, source_ordinal, name, name_normalized, raw_value_json FROM entity_name "
                            "WHERE observation_id=? ORDER BY source_path, source_ordinal",
                            (observation_id,),
                        ).fetchall()
                        if sorted(actual) != sorted(wanted):
                            errors.append({"ordinal": ordinal, "kind": "CHILD_MISMATCH", "table": table})
                    else:
                        if table == "relationship_period":
                            columns = "source_ordinal, period_type, start_date, end_date, raw_value_json"
                        else:
                            columns = "source_ordinal, raw_value_json"
                        actual = conn.execute(
                            f"SELECT {columns} FROM {table} "
                            "WHERE observation_id=? ORDER BY source_ordinal",
                            (observation_id,),
                        ).fetchall()
                        if actual != wanted:
                            errors.append({"ordinal": ordinal, "kind": "CHILD_MISMATCH", "table": table})
                    counts[table] += len(wanted)
                counts["verified_records"] += 1
            except (ValueError, TypeError, zlib.error, json.JSONDecodeError) as exc:
                errors.append({"ordinal": ordinal, "kind": "DECODE_ERROR", "error": str(exc)})
            if is_sample and ordinal >= last_ordinal:
                break
        if set(positions) != found:
            errors.append({"kind": "SOURCE_ORDINALS_NOT_FOUND", "ordinals": sorted(set(positions) - found)})
        for table, checked in counts.items():
            staged_count = conn.execute(f"SELECT COUNT(*) FROM {table if table != 'verified_records' else 'source_observation'}").fetchone()[0]
            if staged_count != checked:
                errors.append({"kind": "TABLE_COUNT_MISMATCH", "table": table,
                               "source_count": checked, "staged_count": staged_count})
        return {
            "status": "PASS" if not errors else "FAIL",
            "level": level, "is_sample": bool(is_sample),
            "source_archive_sha256_matches": True,
            "source_records_verified": counts["verified_records"],
            "tier1_elements_verified": {k: v for k, v in counts.items() if k != "verified_records"},
            "error_count": len(errors),
            "examples": errors[:15],
            "limitations": [
                "Parser-level structural comparison, not byte-for-byte original JSON.",
                "Checks only staged ordinals; samples do not prove a complete source import.",
                "For RR this independently uses ijson, not the production line-based record iterator.",
            ],
        }
    finally:
        conn.close()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--source", required=True, help="Original JSON or JSON ZIP")
    ap.add_argument("--db", required=True, help="Staged evidence SQLite database")
    ap.add_argument("--out", help="Optional JSON verification report")
    args = ap.parse_args()
    report = verify(args.source, args.db)
    body = json.dumps(report, indent=2, ensure_ascii=False)
    if args.out:
        target = Path(args.out)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body + "\n", encoding="utf-8")
    print(body)
    return 0 if report["status"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
