#!/usr/bin/env python3
"""Migrate an existing GLEIF Level 1 SQLite index without re-downloading data.

Usage: python3 code/migrate_gleif_lookup_key.py data/processed/gleif_lei.sqlite
"""
import argparse
import sqlite3
from build_gleif_lei_index import backfill_lookup_keys, create_indexes


def migrate(conn):
    """Upgrade a legacy Level 1 index in place; safe to rerun."""
    columns = {row[1] for row in conn.execute("PRAGMA table_info(lei_entities)")}
    if not columns:
        raise ValueError("Not a GLEIF Level 1 database: missing lei_entities")
    if "legal_name_lookup_key" not in columns:
        conn.execute("ALTER TABLE lei_entities ADD COLUMN legal_name_lookup_key TEXT")
        conn.commit()
    backfill_lookup_keys(conn)
    create_indexes(conn)
    count = conn.execute("SELECT count(*) FROM lei_entities WHERE legal_name_lookup_key IS NULL").fetchone()[0]
    if count:
        raise RuntimeError(f"{count} lookup keys remain unpopulated")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database")
    args = parser.parse_args()
    conn = sqlite3.connect(args.database)
    try:
        migrate(conn)
        print("GLEIF lookup-key migration complete")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
