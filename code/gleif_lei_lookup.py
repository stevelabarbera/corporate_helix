"""
M4.2 — Local GLEIF Level 1 lookup, backed by the SQLite index built by
build_gleif_lei_index.py.

Purpose: given a bare LEI from a Level 2 relationship record, resolve it to
a legal name / jurisdiction / status without requiring a human to supply
--name / --jurisdiction flags by hand.

Resolution outcomes are explicit, not implicit. Every lookup returns a
LeiResolution with a status of:

    RESOLVED           found in the local Level 1 index
    UNRESOLVED_RETRY    not found in the current snapshot; may resolve on a
                         later index rebuild, no human action needed
    UNRESOLVED_TERMINAL known not resolvable (e.g. explicit GLEIF reporting
                         exception). Not wired to a data source yet — the
                         classifier below always returns UNRESOLVED_RETRY
                         for a miss. Reporting-exception data is M4.5 scope.
                         The status is defined now so downstream code
                         (adapter, seed generator, review queue) has a
                         stable contract to branch on before that data
                         exists.

A miss is never silently treated as "no relationship" or given an invented
name. The caller decides what to do with an unresolved LEI; this module
only classifies it.
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

RESOLVED = "RESOLVED"
UNRESOLVED_RETRY = "UNRESOLVED_RETRY"
UNRESOLVED_TERMINAL = "UNRESOLVED_TERMINAL"


@dataclass
class LeiResolution:
    lei: str
    status: str  # RESOLVED | UNRESOLVED_RETRY | UNRESOLVED_TERMINAL
    legal_name: Optional[str] = None
    jurisdiction: Optional[str] = None
    entity_status: Optional[str] = None
    registration_status: Optional[str] = None

    @property
    def display_name(self) -> str:
        # Never invent a name. If unresolved, the caller should keep the
        # bare LEI visible as the display value so it's obviously not a
        # real legal name rather than something that looks confidently wrong.
        return self.legal_name if self.status == RESOLVED else self.lei


class GleifLeiIndex:
    """
    Thin, read-only wrapper around the SQLite index produced by
    build_gleif_lei_index.py. Safe to hold open across many lookups.
    """

    def __init__(self, db_path: str | Path):
        self.db_path = Path(db_path)
        if not self.db_path.is_file():
            raise FileNotFoundError(
                f"GLEIF LEI index not found at {self.db_path}. "
                "Build it first with code/build_gleif_lei_index.py."
            )
        # Read-only connection: this index is a build artifact, never
        # written to from the RR canonicalization path.
        uri = f"file:{self.db_path.as_posix()}?mode=ro"
        self._conn = sqlite3.connect(uri, uri=True)
        self._conn.row_factory = sqlite3.Row

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "GleifLeiIndex":
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def metadata(self) -> dict[str, str]:
        rows = self._conn.execute("SELECT key, value FROM index_metadata").fetchall()
        return {r["key"]: r["value"] for r in rows}

    def _row(self, lei: str) -> Optional[sqlite3.Row]:
        return self._conn.execute(
            "SELECT legal_name, legal_jurisdiction, entity_status, registration_status "
            "FROM lei_entities WHERE lei = ?",
            (lei,),
        ).fetchone()

    def _classify_miss(self, lei: str) -> str:
        # Reporting-exception lookup (M4.5) would go here. Until that data
        # source exists, every miss is retry-eligible rather than terminal —
        # UNRESOLVED_TERMINAL requires positive evidence the LEI will never
        # resolve, which we don't have yet.
        return UNRESOLVED_RETRY

    def lookup(self, lei: Optional[str]) -> LeiResolution:
        if not lei:
            return LeiResolution(lei=lei or "", status=UNRESOLVED_RETRY)

        row = self._row(lei)
        if row is None:
            return LeiResolution(lei=lei, status=self._classify_miss(lei))

        return LeiResolution(
            lei=lei,
            status=RESOLVED,
            legal_name=row["legal_name"],
            jurisdiction=row["legal_jurisdiction"],
            entity_status=row["entity_status"],
            registration_status=row["registration_status"],
        )
