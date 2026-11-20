#!/usr/bin/env python3
"""Build a NEW, isolated GLEIF Tier-1 evidence database; never replace a live index.

Stores each parsed source record as compressed canonical JSON, source archive
SHA-256, and selective queryable one-to-many child structures. Existing LEI/RR
indexes remain untouched. This is an evidence *staging* prototype, not a
production publication mechanism or a byte-for-byte record archive.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import zlib

from audit_gleif_cardinality import iter_source


SCHEMA = """
PRAGMA foreign_keys=ON;
CREATE TABLE source_snapshot (
  snapshot_id INTEGER PRIMARY KEY,
  source_level TEXT NOT NULL,
  source_path TEXT NOT NULL,
  source_archive_sha256 TEXT NOT NULL,
  record_count INTEGER NOT NULL DEFAULT 0,
  is_sample INTEGER NOT NULL
);
CREATE TABLE source_observation (
  observation_id INTEGER PRIMARY KEY,
  snapshot_id INTEGER NOT NULL REFERENCES source_snapshot(snapshot_id),
  source_ordinal INTEGER NOT NULL,
  source_record_sha256 TEXT NOT NULL,
  source_record_zlib BLOB NOT NULL,
  record_identifier TEXT,
  UNIQUE(snapshot_id, source_ordinal)
);
CREATE INDEX source_observation_identifier_idx ON source_observation(record_identifier);
CREATE TABLE entity_name (
  observation_id INTEGER NOT NULL REFERENCES source_observation(observation_id),
  source_path TEXT NOT NULL,
  source_ordinal INTEGER NOT NULL,
  name TEXT,
  name_normalized TEXT,
  raw_value_json TEXT NOT NULL,
  PRIMARY KEY(observation_id, source_path, source_ordinal)
);
CREATE INDEX entity_name_match_idx ON entity_name(name_normalized);
CREATE TABLE entity_event (
  observation_id INTEGER NOT NULL REFERENCES source_observation(observation_id),
  source_ordinal INTEGER NOT NULL,
  raw_value_json TEXT NOT NULL,
  PRIMARY KEY(observation_id, source_ordinal)
);
CREATE TABLE entity_successor (
  observation_id INTEGER NOT NULL REFERENCES source_observation(observation_id),
  source_ordinal INTEGER NOT NULL,
  raw_value_json TEXT NOT NULL,
  PRIMARY KEY(observation_id, source_ordinal)
);
CREATE TABLE relationship_period (
  observation_id INTEGER NOT NULL REFERENCES source_observation(observation_id),
  source_ordinal INTEGER NOT NULL,
  period_type TEXT,
  start_date TEXT,
  end_date TEXT,
  raw_value_json TEXT NOT NULL,
  PRIMARY KEY(observation_id, source_ordinal)
);
CREATE TABLE relationship_qualifier (
  observation_id INTEGER NOT NULL REFERENCES source_observation(observation_id),
  source_ordinal INTEGER NOT NULL,
  raw_value_json TEXT NOT NULL,
  PRIMARY KEY(observation_id, source_ordinal)
);
CREATE TABLE evidence_counts (name TEXT PRIMARY KEY, count INTEGER NOT NULL);
"""


def items(value):
    """Normalize object-or-array occurrence without dropping either."""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def leaf(value):
    if isinstance(value, dict):
        return value.get("$")
    return value


def canonical(value):
    # ijson uses Decimal for non-integer numeric values. Refuse coercion,
    # because converting Decimal to string would silently change JSON types.
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)


def digest_file(path, chunk=4 * 1024 * 1024):
    h = hashlib.sha256()
    with open(path, "rb") as stream:
        while True:
            data = stream.read(chunk)
            if not data:
                return h.hexdigest()
            h.update(data)


def record_payload(record):
    text = canonical(record)
    raw = text.encode("utf-8")
    return hashlib.sha256(raw).hexdigest(), zlib.compress(raw, level=6)


def add_children(conn, level, observation_id, record):
    count = {}
    if level == "lei":
        entity = record.get("Entity") or {}
        name_groups = [
            ("Entity.LegalName", items(entity.get("LegalName"))),
            ("Entity.OtherEntityNames.OtherEntityName",
             items((entity.get("OtherEntityNames") or {}).get("OtherEntityName"))),
            ("Entity.TransliteratedOtherEntityNames.TransliteratedOtherEntityName",
             items((entity.get("TransliteratedOtherEntityNames") or {}).get("TransliteratedOtherEntityName"))),
        ]
        total = 0
        for path, values in name_groups:
            for ordinal, obj in enumerate(values):
                name = leaf(obj)
                if name is not None and not isinstance(name, str):
                    raise ValueError(f"Unexpected entity-name type at {path}: {type(name)}")
                conn.execute(
                    "INSERT INTO entity_name VALUES (?,?,?,?,?,?)",
                    (observation_id, path, ordinal, name,
                     name.strip().casefold() if isinstance(name, str) else None,
                     canonical(obj)),
                )
                total += 1
        count["entity_name"] = total
        for field, table in (
            ("LegalEntityEvents", "entity_event"),
            ("SuccessorEntity", "entity_successor"),
        ):
            if field == "LegalEntityEvents":
                values = items((entity.get(field) or {}).get("LegalEntityEvent"))
            else:
                values = items(entity.get(field))
            for ordinal, obj in enumerate(values):
                conn.execute(f"INSERT INTO {table} VALUES (?,?,?)",
                             (observation_id, ordinal, canonical(obj)))
            count[table] = len(values)
    else:
        rr = record.get("RelationshipRecord", record)
        relationship = rr.get("Relationship") or {}
        periods = items((relationship.get("RelationshipPeriods") or {}).get("RelationshipPeriod"))
        for ordinal, obj in enumerate(periods):
            if not isinstance(obj, dict):
                raise ValueError("Period is not a JSON object")
            conn.execute("INSERT INTO relationship_period VALUES (?,?,?,?,?,?)",
                         (observation_id, ordinal, leaf(obj.get("PeriodType")),
                          leaf(obj.get("StartDate")), leaf(obj.get("EndDate")),
                          canonical(obj)))
        count["relationship_period"] = len(periods)
        qualifiers = items((relationship.get("RelationshipQualifiers") or {}).get("RelationshipQualifier"))
        for ordinal, obj in enumerate(qualifiers):
            conn.execute("INSERT INTO relationship_qualifier VALUES (?,?,?)",
                         (observation_id, ordinal, canonical(obj)))
        count["relationship_qualifier"] = len(qualifiers)
    return count


def build(level, source, out, max_records=None, progress_every=100000):
    source = Path(source).resolve()
    target = Path(out).resolve()
    if not source.is_file():
        raise ValueError(f"Source not found: {source}")
    if max_records is not None and max_records < 1:
        raise ValueError("max_records must be positive")
    if source == target:
        raise ValueError("Refusing source/output path collision")
    target.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation; never modify an existing production or prior evidence DB.
    with open(target, "xb"):
        pass
    conn = None
    try:
        conn = sqlite3.connect(target)
        conn.executescript(SCHEMA)
        conn.execute(
            "INSERT INTO source_snapshot (source_level, source_path, source_archive_sha256, is_sample) VALUES (?,?,?,?)",
            (level, str(source), digest_file(source), int(max_records is not None)),
        )
        counters = {"source_observation": 0}
        for ordinal, record in enumerate(iter_source(str(source), level), 1):
            record_hash, payload = record_payload(record)
            if level == "lei":
                identifier = leaf(record.get("LEI"))
            else:
                rr = record.get("RelationshipRecord", record)
                rel = rr.get("Relationship") or {}
                identifier = str(leaf((rel.get("StartNode") or {}).get("NodeID")) or "")
                identifier += "|" + str(leaf((rel.get("EndNode") or {}).get("NodeID")) or "")
                identifier += "|" + str(leaf(rel.get("RelationshipType")) or "")
            cursor = conn.execute(
                "INSERT INTO source_observation (snapshot_id, source_ordinal, source_record_sha256, source_record_zlib, record_identifier) VALUES (1,?,?,?,?)",
                (ordinal, record_hash, payload, identifier),
            )
            children = add_children(conn, level, cursor.lastrowid, record)
            counters["source_observation"] += 1
            for name, n in children.items():
                counters[name] = counters.get(name, 0) + n
            if ordinal % 1000 == 0:
                conn.commit()
            if progress_every and ordinal % progress_every == 0:
                print(f"Staged {ordinal:,} records", file=sys.stderr)
            if max_records is not None and ordinal >= max_records:
                break
        conn.execute("UPDATE source_snapshot SET record_count=? WHERE snapshot_id=1",
                     (counters["source_observation"],))
        for name, value in counters.items():
            conn.execute("INSERT INTO evidence_counts VALUES (?,?)", (name, value))
        conn.commit()
        for table, expected in counters.items():
            actual = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
            if actual != expected:
                raise RuntimeError(f"Count mismatch in {table}: {actual} != {expected}")
        bad = conn.execute("PRAGMA foreign_key_check").fetchall()
        if bad:
            raise RuntimeError(f"Foreign-key violations: {bad[:3]}")
        # Verify record hash from the persisted compressed source record.
        for compressed, expected in conn.execute(
            "SELECT source_record_zlib, source_record_sha256 FROM source_observation"
        ):
            if hashlib.sha256(zlib.decompress(compressed)).hexdigest() != expected:
                raise RuntimeError("Stored source record hash mismatch")
        return counters
    except Exception:
        if conn is not None:
            conn.close()
            conn = None
        target.unlink(missing_ok=True)
        raise
    finally:
        if conn is not None:
            conn.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--level", choices=("lei", "rr"), required=True)
    parser.add_argument("--source", required=True)
    parser.add_argument("--out", required=True, help="NEW output path only; existing files are rejected")
    parser.add_argument("--max-records", type=int)
    parser.add_argument("--progress-every", type=int, default=100000)
    args = parser.parse_args()
    result = build(args.level, args.source, args.out, args.max_records, args.progress_every)
    print(json.dumps({"status": "STAGED_ONLY", "level": args.level,
                      "is_sample": args.max_records is not None, "counts": result}, indent=2))


if __name__ == "__main__":
    main()
