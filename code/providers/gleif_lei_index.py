from __future__ import annotations

import sqlite3
from pathlib import Path


def lookup_lei(db_path: str | Path, lei: str) -> dict | None:
    """
    Look up one LEI in the local GLEIF Level 1 SQLite index.

    Returns the complete lei_entities row as a dict, or None when the LEI
    is not present.

    Missing Level 1 enrichment does NOT mean a Level 2 relationship is
    invalid. Callers must preserve the RR relationship and may fall back
    to the bare LEI as the display identity.
    """
    if not lei:
        return None

    path = Path(db_path)

    if not path.is_file():
        raise FileNotFoundError(f"GLEIF Level 1 index not found: {path}")

    conn = sqlite3.connect(str(path))

    try:
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA query_only=ON")

        row = conn.execute(
            """
            SELECT *
            FROM lei_entities
            WHERE lei = ?
            LIMIT 1
            """,
            (lei.strip(),),
        ).fetchone()

        return dict(row) if row else None

    except sqlite3.OperationalError as exc:
        raise RuntimeError(
            f"Unable to query GLEIF Level 1 index {path}: {exc}"
        ) from exc

    finally:
        conn.close()


def enrichment_state(record: dict | None) -> str:
    """
    Classify the result of a Level 1 endpoint lookup.
    """
    if record is None:
        return "UNRESOLVED_LEVEL1"

    if record.get("legal_name") and record.get("legal_jurisdiction"):
        return "RESOLVED"

    return "PARTIAL_ENRICHMENT"
