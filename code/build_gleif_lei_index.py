#!/usr/bin/env python3
"""
Build a local SQLite index from the GLEIF Level 1 (LEI2) Golden Copy.

Designed for multi-GB GLEIF files:
- streams with ijson
- never loads the full JSON into memory
- commits in batches
- uses UPSERT, so interrupted builds are safe to rerun
- preserves core identity/provenance fields needed to enrich Level 2 RR records

Example:

python3 code/build_gleif_lei_index.py \
    --file /path/to/20260817-0800-gleif-goldencopy-lei2-golden-copy.json \
    --out data/processed/gleif_lei.sqlite
"""

import argparse
import os
import sqlite3
import sys
import time

import ijson


DEFAULT_PATH = "records.item"
DEFAULT_BATCH_SIZE = 10_000
DEFAULT_PROGRESS_EVERY = 250_000


# Known malformed GLEIF source sequence observed in the 2026-08-04
# Level 1 Golden Copy. We repair only this exact byte pattern while streaming.
KNOWN_BAD_SEQUENCE = b"},."
KNOWN_GOOD_SEQUENCE = b"},"


class RepairingBinaryReader:
    """
    Minimal binary stream wrapper for ijson.

    Replaces only the exact known malformed byte sequence b'},.' -> b'},'
    across chunk boundaries. Every repair is counted and its approximate
    source byte offset is recorded. Any other malformed JSON still causes
    ijson to fail normally.
    """

    def __init__(self, raw, *, chunk_size=1024 * 1024):
        self.raw = raw
        self.chunk_size = chunk_size
        self._buffer = bytearray()
        self._eof = False
        self._source_pos = 0
        self.repairs = []

    def _fill(self, min_bytes=1):
        while len(self._buffer) < min_bytes and not self._eof:
            chunk = self.raw.read(self.chunk_size)
            if not chunk:
                self._eof = True
                break

            base = self._source_pos
            self._source_pos += len(chunk)

            combined = bytes(self._buffer) + chunk
            search_from = 0
            repaired = bytearray()

            while True:
                i = combined.find(KNOWN_BAD_SEQUENCE, search_from)
                if i == -1:
                    repaired.extend(combined[search_from:])
                    break

                repaired.extend(combined[search_from:i])
                repaired.extend(KNOWN_GOOD_SEQUENCE)

                absolute = base - len(self._buffer) + i
                self.repairs.append(absolute)

                search_from = i + len(KNOWN_BAD_SEQUENCE)

            self._buffer = repaired

    def read(self, size=-1):
        if size is None or size < 0:
            while not self._eof:
                self._fill(len(self._buffer) + self.chunk_size)
            data = bytes(self._buffer)
            self._buffer.clear()
            return data

        self._fill(size)
        data = bytes(self._buffer[:size])
        del self._buffer[:size]
        return data

    def readable(self):
        return True


def extract_value(field):
    """GLEIF Golden Copy wraps many leaf values as {'$': value, ...}."""
    if isinstance(field, dict):
        return field.get("$")
    return field


def clean(value):
    if value is None:
        return None
    if isinstance(value, str):
        value = value.strip()
        return value or None
    return str(value)


def flatten_record(record):
    entity = record.get("Entity", {}) or {}
    legal_addr = entity.get("LegalAddress", {}) or {}
    hq_addr = entity.get("HeadquartersAddress", {}) or {}
    legal_form = entity.get("LegalForm", {}) or {}
    registration = record.get("Registration", {}) or {}

    lei = clean(extract_value(record.get("LEI", {})))
    legal_name = clean(extract_value(entity.get("LegalName", {})))

    return {
        "lei": lei,
        "legal_name": legal_name,
        "legal_name_normalized": legal_name.casefold() if legal_name else None,

        "legal_jurisdiction": clean(
            extract_value(entity.get("LegalJurisdiction", {}))
        ),
        "entity_status": clean(
            extract_value(entity.get("EntityStatus", {}))
        ),
        "entity_category": clean(
            extract_value(entity.get("EntityCategory", {}))
        ),

        "legal_form_code": clean(
            extract_value(legal_form.get("EntityLegalFormCode", {}))
        ),
        "other_legal_form": clean(
            extract_value(legal_form.get("OtherLegalForm", {}))
        ),

        "legal_address_country": clean(
            extract_value(legal_addr.get("Country", {}))
        ),
        "legal_address_region": clean(
            extract_value(legal_addr.get("Region", {}))
        ),
        "legal_address_city": clean(
            extract_value(legal_addr.get("City", {}))
        ),

        "hq_country": clean(
            extract_value(hq_addr.get("Country", {}))
        ),
        "hq_region": clean(
            extract_value(hq_addr.get("Region", {}))
        ),
        "hq_city": clean(
            extract_value(hq_addr.get("City", {}))
        ),

        "registration_status": clean(
            extract_value(registration.get("RegistrationStatus", {}))
        ),
        "initial_registration_date": clean(
            extract_value(registration.get("InitialRegistrationDate", {}))
        ),
        "last_update_date": clean(
            extract_value(registration.get("LastUpdateDate", {}))
        ),
        "managing_lou": clean(
            extract_value(registration.get("ManagingLOU", {}))
        ),
        "validation_sources": clean(
            extract_value(registration.get("ValidationSources", {}))
        ),
    }


SCHEMA = """
CREATE TABLE IF NOT EXISTS lei_entities (
    lei TEXT PRIMARY KEY,

    legal_name TEXT,
    legal_name_normalized TEXT,

    legal_jurisdiction TEXT,
    entity_status TEXT,
    entity_category TEXT,

    legal_form_code TEXT,
    other_legal_form TEXT,

    legal_address_country TEXT,
    legal_address_region TEXT,
    legal_address_city TEXT,

    hq_country TEXT,
    hq_region TEXT,
    hq_city TEXT,

    registration_status TEXT,
    initial_registration_date TEXT,
    last_update_date TEXT,
    managing_lou TEXT,
    validation_sources TEXT
);

CREATE TABLE IF NOT EXISTS index_metadata (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""


UPSERT = """
INSERT INTO lei_entities (
    lei,
    legal_name,
    legal_name_normalized,
    legal_jurisdiction,
    entity_status,
    entity_category,
    legal_form_code,
    other_legal_form,
    legal_address_country,
    legal_address_region,
    legal_address_city,
    hq_country,
    hq_region,
    hq_city,
    registration_status,
    initial_registration_date,
    last_update_date,
    managing_lou,
    validation_sources
)
VALUES (
    :lei,
    :legal_name,
    :legal_name_normalized,
    :legal_jurisdiction,
    :entity_status,
    :entity_category,
    :legal_form_code,
    :other_legal_form,
    :legal_address_country,
    :legal_address_region,
    :legal_address_city,
    :hq_country,
    :hq_region,
    :hq_city,
    :registration_status,
    :initial_registration_date,
    :last_update_date,
    :managing_lou,
    :validation_sources
)
ON CONFLICT(lei) DO UPDATE SET
    legal_name = excluded.legal_name,
    legal_name_normalized = excluded.legal_name_normalized,
    legal_jurisdiction = excluded.legal_jurisdiction,
    entity_status = excluded.entity_status,
    entity_category = excluded.entity_category,
    legal_form_code = excluded.legal_form_code,
    other_legal_form = excluded.other_legal_form,
    legal_address_country = excluded.legal_address_country,
    legal_address_region = excluded.legal_address_region,
    legal_address_city = excluded.legal_address_city,
    hq_country = excluded.hq_country,
    hq_region = excluded.hq_region,
    hq_city = excluded.hq_city,
    registration_status = excluded.registration_status,
    initial_registration_date = excluded.initial_registration_date,
    last_update_date = excluded.last_update_date,
    managing_lou = excluded.managing_lou,
    validation_sources = excluded.validation_sources;
"""


def configure_database(conn):
    # Good balance for a bulk local build.
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA temp_store=MEMORY;")
    conn.execute("PRAGMA cache_size=-100000;")  # ~100 MB
    conn.execute("PRAGMA foreign_keys=ON;")

    conn.executescript(SCHEMA)
    conn.commit()


def write_metadata(conn, key, value):
    conn.execute(
        """
        INSERT INTO index_metadata(key, value)
        VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (key, str(value)),
    )


def create_indexes(conn):
    print("Creating lookup indexes...", file=sys.stderr)

    conn.executescript(
        """
        CREATE INDEX IF NOT EXISTS idx_lei_entities_legal_name
            ON lei_entities(legal_name_normalized);

        CREATE INDEX IF NOT EXISTS idx_lei_entities_jurisdiction
            ON lei_entities(legal_jurisdiction);

        CREATE INDEX IF NOT EXISTS idx_lei_entities_status
            ON lei_entities(entity_status);

        CREATE INDEX IF NOT EXISTS idx_lei_entities_country
            ON lei_entities(legal_address_country);

        CREATE INDEX IF NOT EXISTS idx_lei_entities_registration_status
            ON lei_entities(registration_status);
        """
    )
    conn.commit()


def flush_batch(conn, batch):
    if not batch:
        return

    conn.executemany(UPSERT, batch)
    conn.commit()
    batch.clear()


def main():
    parser = argparse.ArgumentParser(
        description="Build SQLite LEI index from GLEIF Level 1 Golden Copy."
    )

    parser.add_argument(
        "--file",
        required=True,
        help="Path to uncompressed GLEIF lei2 Golden Copy JSON",
    )

    parser.add_argument(
        "--out",
        default="data/processed/gleif_lei.sqlite",
        help="Output SQLite database",
    )

    parser.add_argument(
        "--path",
        default=DEFAULT_PATH,
        help=f"ijson record path (default: {DEFAULT_PATH})",
    )

    parser.add_argument(
        "--batch-size",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help=f"Rows per SQLite commit (default: {DEFAULT_BATCH_SIZE:,})",
    )

    parser.add_argument(
        "--progress-every",
        type=int,
        default=DEFAULT_PROGRESS_EVERY,
        help=f"Progress interval (default: {DEFAULT_PROGRESS_EVERY:,})",
    )

    args = parser.parse_args()

    if not os.path.isfile(args.file):
        print(f"ERROR: input file does not exist: {args.file}", file=sys.stderr)
        sys.exit(1)

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)

    print("GLEIF Level 1 SQLite index build", file=sys.stderr)
    print(f"  input : {args.file}", file=sys.stderr)
    print(f"  output: {args.out}", file=sys.stderr)
    print(f"  path  : {args.path}", file=sys.stderr)
    print(file=sys.stderr)

    conn = sqlite3.connect(args.out)
    configure_database(conn)

    write_metadata(conn, "source_file", os.path.abspath(args.file))
    write_metadata(conn, "build_status", "running")
    write_metadata(conn, "build_started_unix", int(time.time()))
    conn.commit()

    total_scanned = 0
    total_indexed = 0
    skipped_missing_lei = 0
    batch = []

    started = time.time()

    try:
        with open(args.file, "rb") as raw_f:
            f = RepairingBinaryReader(raw_f)
            for record in ijson.items(f, args.path):
                total_scanned += 1

                flat = flatten_record(record)

                if not flat["lei"]:
                    skipped_missing_lei += 1
                    continue

                batch.append(flat)
                total_indexed += 1

                if len(batch) >= args.batch_size:
                    flush_batch(conn, batch)

                if (
                    args.progress_every
                    and total_scanned % args.progress_every == 0
                ):
                    elapsed = time.time() - started
                    rate = total_scanned / elapsed if elapsed else 0

                    print(
                        f"  scanned={total_scanned:,} "
                        f"indexed={total_indexed:,} "
                        f"skipped={skipped_missing_lei:,} "
                        f"rate={rate:,.0f} records/sec",
                        file=sys.stderr,
                    )

        flush_batch(conn, batch)

        if f.repairs:
            print(
                f"  repaired known GLEIF syntax defects: {len(f.repairs):,}",
                file=sys.stderr,
            )
            for offset in f.repairs:
                print(
                    f"    repaired {KNOWN_BAD_SEQUENCE!r} -> "
                    f"{KNOWN_GOOD_SEQUENCE!r} near byte {offset:,}",
                    file=sys.stderr,
                )

        write_metadata(conn, "source_syntax_repairs", len(f.repairs))
        if f.repairs:
            write_metadata(
                conn,
                "source_syntax_repair_offsets",
                ",".join(str(x) for x in f.repairs),
            )

        create_indexes(conn)

        write_metadata(conn, "records_scanned", total_scanned)
        write_metadata(conn, "records_indexed", total_indexed)
        write_metadata(conn, "records_skipped_missing_lei", skipped_missing_lei)
        write_metadata(conn, "build_completed_unix", int(time.time()))
        write_metadata(conn, "build_status", "complete")
        conn.commit()

    except KeyboardInterrupt:
        flush_batch(conn, batch)

        write_metadata(conn, "records_scanned", total_scanned)
        write_metadata(conn, "records_indexed", total_indexed)
        write_metadata(conn, "build_status", "interrupted")
        conn.commit()

        print(
            "\nInterrupted. Committed rows are preserved. "
            "Rerunning is safe because LEI is the primary key.",
            file=sys.stderr,
        )
        sys.exit(130)

    finally:
        conn.close()

    elapsed = time.time() - started

    print(file=sys.stderr)
    print("Build complete.", file=sys.stderr)
    print(f"  scanned : {total_scanned:,}", file=sys.stderr)
    print(f"  indexed : {total_indexed:,}", file=sys.stderr)
    print(f"  skipped : {skipped_missing_lei:,}", file=sys.stderr)
    print(f"  seconds : {elapsed:,.1f}", file=sys.stderr)
    print(f"  database: {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()