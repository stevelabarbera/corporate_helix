#!/usr/bin/env python3
"""Read-only source validation of a real GLEIF L1 database.

Creates a temporary SQLite backup, migrates only the backup, and checks
record preservation and normalized name lookup. Does not modify the source.
"""
import argparse
import json
import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from migrate_gleif_lookup_key import migrate
from root_entity_resolver import find_seed_matches


def validate(source):
    source = Path(source).resolve()
    if not source.is_file():
        raise FileNotFoundError(source)
    with tempfile.TemporaryDirectory(prefix="helix-gleif-validation-") as directory:
        copied = Path(directory) / "gleif_lei.sqlite"
        with sqlite3.connect(f"file:{source}?mode=ro", uri=True) as original:
            before = original.execute("SELECT count(*) FROM lei_entities").fetchone()[0]
            with sqlite3.connect(copied) as backup:
                original.backup(backup)
        with sqlite3.connect(copied) as conn:
            conn.row_factory = sqlite3.Row
            migrate(conn)
            migrate(conn)
            after = conn.execute("SELECT count(*) FROM lei_entities").fetchone()[0]
            integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
            null_keys = conn.execute(
                "SELECT count(*) FROM lei_entities WHERE legal_name_lookup_key IS NULL"
            ).fetchone()[0]
            citrix = conn.execute(
                "SELECT lei FROM lei_entities WHERE lei = ?",
                ("HCTKJGUQOPZ5NBK7NP58",),
            ).fetchone()
            citrix_match = (
                any(row["lei"] == "HCTKJGUQOPZ5NBK7NP58"
                    for row in find_seed_matches(conn, "Citrix Systems Inc"))
                if citrix else None
            )
            report = {
                "source": str(source),
                "source_modified": False,
                "rows_before": before,
                "rows_after": after,
                "integrity": integrity,
                "null_lookup_keys": null_keys,
                "citrix_present": bool(citrix),
                "citrix_resolves_by_name": citrix_match,
                "passed": (before == after and integrity == "ok"
                           and null_keys == 0 and citrix_match is not False),
            }
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lei-index", default="data/processed/gleif_lei.sqlite")
    args = parser.parse_args()
    result = validate(args.lei_index)
    print(json.dumps(result, indent=2))
    sys.exit(0 if result["passed"] else 1)
