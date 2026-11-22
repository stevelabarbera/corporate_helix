#!/usr/bin/env python3
"""Build a compact, additive GLEIF Level 1 alias lookup from an immutable ZIP.

Only aliases and the LEI/ordinal needed to trace them are stored. Does not
store entire source records, and will never overwrite a pre-existing file.
A complete source scan is required for non-sample status.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path
import sqlite3
import sys

from audit_gleif_cardinality import iter_source
from build_gleif_tier1_evidence import digest_file, items, leaf


SCHEMA = """
CREATE TABLE source_snapshot (
  source_level TEXT NOT NULL CHECK(source_level='lei'),
  source_path TEXT NOT NULL,
  source_archive_sha256 TEXT NOT NULL,
  record_count INTEGER NOT NULL,
  alias_count INTEGER NOT NULL,
  is_sample INTEGER NOT NULL CHECK(is_sample IN (0,1))
);
CREATE TABLE source_observation (
  observation_id INTEGER PRIMARY KEY,
  source_ordinal INTEGER NOT NULL UNIQUE,
  record_identifier TEXT NOT NULL
);
CREATE TABLE entity_name (
  observation_id INTEGER NOT NULL REFERENCES source_observation(observation_id),
  source_path TEXT NOT NULL,
  source_ordinal INTEGER NOT NULL,
  name TEXT NOT NULL,
  name_normalized TEXT NOT NULL,
  raw_value_json TEXT NOT NULL,
  PRIMARY KEY(observation_id, source_path, source_ordinal)
);
CREATE INDEX entity_name_match_idx ON entity_name(name_normalized);
CREATE INDEX source_observation_lei_idx ON source_observation(record_identifier);
"""


def record_aliases(record):
    """Keep all source-reported other/transliterated names, in source order."""
    entity = record.get("Entity") or {}
    for path, values in (
        ("Entity.OtherEntityNames.OtherEntityName",
         items((entity.get("OtherEntityNames") or {}).get("OtherEntityName"))),
        ("Entity.TransliteratedOtherEntityNames.TransliteratedOtherEntityName",
         items((entity.get("TransliteratedOtherEntityNames") or {}).get("TransliteratedOtherEntityName"))),
    ):
        for ordinal, obj in enumerate(values):
            name = leaf(obj)
            if not isinstance(name, str):
                raise ValueError(f"Invalid alias name at {path}[{ordinal}]: {name!r}")
            yield path, ordinal, name, name.strip().casefold(), json.dumps(
                obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            )


def build(source, out, max_records=None, progress_every=100000):
    source, target = Path(source).resolve(), Path(out).resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    if max_records is not None and max_records < 1:
        raise ValueError("max_records must be positive")
    if source == target:
        raise ValueError("Source/output collision")
    target.parent.mkdir(parents=True, exist_ok=True)
    with open(target, "xb"):
        pass
    db = None
    try:
        db = sqlite3.connect(target)
        db.execute("PRAGMA foreign_keys=ON")
        db.executescript(SCHEMA)
        seen = 0
        alias_count = 0
        alias_entities = 0
        for seen, record in enumerate(iter_source(str(source), "lei"), 1):
            aliases = list(record_aliases(record))
            if aliases:
                lei = leaf(record.get("LEI"))
                if not isinstance(lei, str) or not lei.strip():
                    raise ValueError(f"Alias-bearing GLEIF record {seen} lacks LEI")
                cursor = db.execute(
                    "INSERT INTO source_observation (source_ordinal,record_identifier) VALUES (?,?)",
                    (seen, lei),
                )
                db.executemany(
                    """INSERT INTO entity_name
                      (observation_id,source_path,source_ordinal,name,name_normalized,raw_value_json)
                      VALUES (?,?,?,?,?,?)""",
                    ((cursor.lastrowid, *entry) for entry in aliases),
                )
                alias_entities += 1
                alias_count += len(aliases)
            if seen % 10000 == 0:
                db.commit()
            if progress_every and seen % progress_every == 0:
                print(f"Scanned {seen:,} records; indexed {alias_count:,} aliases", file=sys.stderr)
            if max_records and seen >= max_records:
                break
        if not seen:
            raise ValueError("Source contains no GLEIF Level 1 records")
        db.execute(
            "INSERT INTO source_snapshot VALUES ('lei',?,?,?,?,?)",
            (str(source), digest_file(source), seen, alias_count,
             int(max_records is not None)),
        )
        db.commit()
        if db.execute("SELECT COUNT(*) FROM entity_name").fetchone()[0] != alias_count:
            raise RuntimeError("Alias count mismatch")
        if db.execute("SELECT COUNT(*) FROM source_observation").fetchone()[0] != alias_entities:
            raise RuntimeError("Alias-bearing LEI count mismatch")
        if db.execute("PRAGMA foreign_key_check").fetchall():
            raise RuntimeError("Foreign key validation failed")
        return {
            "status": "BUILT_UNVERIFIED",
            "records_scanned": seen,
            "alias_entries": alias_count,
            "alias_bearing_entities": alias_entities,
            "is_sample": max_records is not None,
            "source_archive_sha256": digest_file(source),
            "out": str(target),
        }
    except BaseException:
        if db is not None:
            db.close()
            db = None
        target.unlink(missing_ok=True)
        raise
    finally:
        if db is not None:
            db.close()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source", required=True, help="Original Level 1 JSON/ZIP source")
    p.add_argument("--out", required=True, help="NEW SQLite path; never overwrites")
    p.add_argument("--max-records", type=int, help="Small sample trial; omitted = full source")
    p.add_argument("--progress-every", type=int, default=100000)
    args = p.parse_args()
    print(json.dumps(build(args.source, args.out, args.max_records,
                           args.progress_every), indent=2))


if __name__ == "__main__":
    main()
