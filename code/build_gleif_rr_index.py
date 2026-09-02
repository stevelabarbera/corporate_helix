#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import time
import zipfile


SUPPORTED_TYPES = {
    "IS_DIRECTLY_CONSOLIDATED_BY",
    "IS_ULTIMATELY_CONSOLIDATED_BY",
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS relationships (
    id INTEGER PRIMARY KEY,

    child_lei TEXT NOT NULL,
    parent_lei TEXT NOT NULL,
    relationship_type TEXT NOT NULL,

    relationship_status TEXT,

    relationship_start TEXT,
    relationship_end TEXT,

    accounting_start TEXT,
    accounting_end TEXT,

    document_filing_start TEXT,
    document_filing_end TEXT,

    registration_status TEXT,
    initial_registration_date TEXT,
    last_update_date TEXT,

    managing_lou TEXT,
    validation_sources TEXT,
    validation_documents TEXT,
    validation_reference TEXT,

    source_file TEXT
);

CREATE TABLE IF NOT EXISTS index_metadata (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_relationship_unique
    ON relationships(
        child_lei,
        parent_lei,
        relationship_type
    );
"""


def _v(obj, *path):
    for part in path:
        if not isinstance(obj, dict):
            return None
        obj = obj.get(part)

    if isinstance(obj, dict) and "$" in obj:
        return obj.get("$")

    return obj


def configure_database(conn):
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA temp_store=MEMORY;")
    conn.execute("PRAGMA cache_size=-100000;")
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


def create_lookup_indexes(conn):
    print("Creating relationship lookup indexes...", file=sys.stderr)

    conn.executescript(
        """
        CREATE INDEX IF NOT EXISTS idx_relationship_child
            ON relationships(child_lei);

        CREATE INDEX IF NOT EXISTS idx_relationship_parent
            ON relationships(parent_lei);

        CREATE INDEX IF NOT EXISTS idx_relationship_type
            ON relationships(relationship_type);
        """
    )

    conn.commit()


def records(path):
    with zipfile.ZipFile(path) as z:
        names = z.namelist()

        if not names:
            raise RuntimeError(f"ZIP contains no files: {path}")

        with z.open(names[0]) as f:
            buf = []
            depth = 0
            active = False

            for raw in f:
                s = raw.decode("utf-8")

                if not active and '"RelationshipRecord"' in s:
                    active = True
                    buf = ["{\n", s]
                    depth = 1 + s.count("{") - s.count("}")

                elif active:
                    buf.append(s)
                    depth += s.count("{") - s.count("}")

                    if depth == 0:
                        yield json.loads(
                            "".join(buf).rstrip().rstrip(",")
                        )
                        active = False
                        buf = []


def relationship_periods(rel):
    """
    Return periods keyed by GLEIF PeriodType.

    Example:
        {
            "RELATIONSHIP_PERIOD": (start, end),
            "ACCOUNTING_PERIOD": (start, end),
            "DOCUMENT_FILING_PERIOD": (start, end),
        }
    """
    result = {}

    container = rel.get("RelationshipPeriods") or {}
    periods = container.get("RelationshipPeriod") if isinstance(container, dict) else None

    if not periods:
        return result

    if isinstance(periods, dict):
        periods = [periods]

    for period in periods:
        if not isinstance(period, dict):
            continue

        period_type = _v(period, "PeriodType")

        if not period_type:
            continue

        result[period_type] = (
            _v(period, "StartDate"),
            _v(period, "EndDate"),
        )

    return result


UPSERT = """
INSERT INTO relationships (
    child_lei,
    parent_lei,
    relationship_type,
    relationship_status,

    relationship_start,
    relationship_end,

    accounting_start,
    accounting_end,

    document_filing_start,
    document_filing_end,

    registration_status,
    initial_registration_date,
    last_update_date,

    managing_lou,
    validation_sources,
    validation_documents,
    validation_reference,

    source_file
)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)

ON CONFLICT(
    child_lei,
    parent_lei,
    relationship_type
)
DO UPDATE SET
    relationship_status = excluded.relationship_status,

    relationship_start = excluded.relationship_start,
    relationship_end = excluded.relationship_end,

    accounting_start = excluded.accounting_start,
    accounting_end = excluded.accounting_end,

    document_filing_start = excluded.document_filing_start,
    document_filing_end = excluded.document_filing_end,

    registration_status = excluded.registration_status,
    initial_registration_date = excluded.initial_registration_date,
    last_update_date = excluded.last_update_date,

    managing_lou = excluded.managing_lou,
    validation_sources = excluded.validation_sources,
    validation_documents = excluded.validation_documents,
    validation_reference = excluded.validation_reference,

    source_file = excluded.source_file
"""


def main():
    ap = argparse.ArgumentParser(
        description="Build local SQLite index from GLEIF Level 2 RR Golden Copy."
    )

    ap.add_argument("--zip", required=True)

    ap.add_argument(
        "--out",
        default="data/processed/gleif_rr.sqlite",
    )

    ap.add_argument(
        "--batch-size",
        type=int,
        default=10_000,
    )

    ap.add_argument(
        "--progress-every",
        type=int,
        default=100_000,
    )

    args = ap.parse_args()

    if not os.path.isfile(args.zip):
        raise SystemExit(f"Input ZIP does not exist: {args.zip}")

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)

    # Rebuild cleanly because the period schema changed.
    if os.path.exists(args.out):
        os.remove(args.out)

    conn = sqlite3.connect(args.out)
    configure_database(conn)

    write_metadata(conn, "source_file", os.path.abspath(args.zip))
    write_metadata(conn, "build_status", "running")
    write_metadata(conn, "build_started_unix", int(time.time()))
    conn.commit()

    scanned = 0
    indexed = 0
    unsupported = 0
    incomplete = 0
    batch = []

    started = time.time()

    try:
        for wrapper in records(args.zip):
            scanned += 1

            rr = wrapper.get("RelationshipRecord", wrapper)
            rel = rr.get("Relationship") or {}
            reg = rr.get("Registration") or {}

            relationship_type = _v(rel, "RelationshipType")

            if relationship_type not in SUPPORTED_TYPES:
                unsupported += 1
                continue

            child_lei = _v(rel, "StartNode", "NodeID")
            parent_lei = _v(rel, "EndNode", "NodeID")

            if not child_lei or not parent_lei:
                incomplete += 1
                continue

            periods = relationship_periods(rel)

            relationship_period = periods.get(
                "RELATIONSHIP_PERIOD",
                (None, None),
            )

            accounting_period = periods.get(
                "ACCOUNTING_PERIOD",
                (None, None),
            )

            filing_period = periods.get(
                "DOCUMENT_FILING_PERIOD",
                (None, None),
            )

            batch.append(
                (
                    child_lei,
                    parent_lei,
                    relationship_type,
                    _v(rel, "RelationshipStatus"),

                    relationship_period[0],
                    relationship_period[1],

                    accounting_period[0],
                    accounting_period[1],

                    filing_period[0],
                    filing_period[1],

                    _v(reg, "RegistrationStatus"),
                    _v(reg, "InitialRegistrationDate"),
                    _v(reg, "LastUpdateDate"),

                    _v(reg, "ManagingLOU"),
                    _v(reg, "ValidationSources"),
                    _v(reg, "ValidationDocuments"),
                    _v(reg, "ValidationReference"),

                    os.path.basename(args.zip),
                )
            )

            indexed += 1

            if len(batch) >= args.batch_size:
                conn.executemany(UPSERT, batch)
                conn.commit()
                batch.clear()

            if args.progress_every and scanned % args.progress_every == 0:
                elapsed = time.time() - started
                rate = scanned / elapsed if elapsed else 0

                print(
                    f"scanned={scanned:,} "
                    f"indexed={indexed:,} "
                    f"unsupported={unsupported:,} "
                    f"incomplete={incomplete:,} "
                    f"rate={rate:,.0f}/sec",
                    file=sys.stderr,
                )

        if batch:
            conn.executemany(UPSERT, batch)
            conn.commit()

        create_lookup_indexes(conn)

        write_metadata(conn, "records_scanned", scanned)
        write_metadata(conn, "records_indexed_supported", indexed)
        write_metadata(conn, "records_unsupported", unsupported)
        write_metadata(conn, "records_incomplete", incomplete)
        write_metadata(conn, "build_completed_unix", int(time.time()))
        write_metadata(conn, "build_status", "complete")
        conn.commit()

    finally:
        conn.close()

    elapsed = time.time() - started

    print()
    print("GLEIF Level 2 relationship index complete.")
    print(f"  scanned     : {scanned:,}")
    print(f"  supported   : {indexed:,}")
    print(f"  unsupported : {unsupported:,}")
    print(f"  incomplete  : {incomplete:,}")
    print(f"  seconds     : {elapsed:,.1f}")
    print(f"  database    : {args.out}")


if __name__ == "__main__":
    main()
