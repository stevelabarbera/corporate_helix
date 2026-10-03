#!/usr/bin/env python3
"""
Regression test for M4.2's GLEIF RR auto-enrichment path.

Bug found 2026-09-25: canonicalize_gleif_rr.py imported
`providers.gleif_lei_lookup.GleifLeiIndex`, but that module didn't exist
under providers/ at all -- ModuleNotFoundError on every invocation, not a
subtle logic bug. The real M4.2 work (a correct GleifLeiIndex, and a
GleifRelationshipRecordAdapter with real auto-enrichment precedence logic)
existed as a working, internally-consistent pair of files -- but loose at
the top level of code/, cross-referencing each other via a relative
import, never wired into the actual CLI entry point. providers/ still had
a stale, pre-M4.2 copy of the adapter with no lei_index parameter at all.
So "M4.2 add automatic GLEIF RR Level 1 enrichment" (commit b8535f9) had
been merged, and a second commit ("work on 4.2", 9e0da96) built the real
logic correctly -- but the CLI script never actually exercised any of it.
The only existing test (test_gleif_rr_vertical_slice.py) always supplied
manual name/jurisdiction overrides, which bypass index lookup entirely by
design, so it could never have caught this: it was testing the adapter's
override precedence, not the SQLite auto-enrichment path at all.

Fix: moved both files into providers/ (git mv, preserving history) so the
CLI's existing `from providers.gleif_rr_adapter import ...` /
`from providers.gleif_lei_lookup import ...` imports resolve to the real,
auto-enrichment-aware code instead of the stale copy.

This test builds a minimal but schema-real SQLite fixture (same columns
`build_gleif_lei_index.py` produces) seeded with two real, confirmed GLEIF
Level 1 records -- Dokobit UAB (Lithuania) and Signicat AS (Norway),
looked up directly against the live GLEIF Level 1 index during a separate
investigation into private-company M&A coverage gaps -- rather than
placeholder LEIs, so this exercises the real lookup path end-to-end
against real data shapes, not just a mock.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))

from providers.gleif_lei_lookup import GleifLeiIndex, RESOLVED, UNRESOLVED_RETRY
from providers.gleif_rr_adapter import GleifRelationshipRecordAdapter

DOKOBIT_LEI = "8945002COKCH510PDI59"
DOKOBIT_NAME = "Dokobit, UAB"
DOKOBIT_JURISDICTION = "LT"

SIGNICAT_LEI = "636700GM6DEIS5MBAV78"
SIGNICAT_NAME = "SIGNICAT AS"
SIGNICAT_JURISDICTION = "NO"

RAW_RECORD = {
    "RelationshipRecord": {
        "Relationship": {
            "StartNode": {"NodeID": {"$": DOKOBIT_LEI}},
            "EndNode": {"NodeID": {"$": SIGNICAT_LEI}},
            "RelationshipType": {"$": "IS_DIRECTLY_CONSOLIDATED_BY"},
            "RelationshipStatus": {"$": "ACTIVE"},
        },
        "Registration": {
            "LastUpdateDate": {"$": "2026-09-25T00:00:00Z"},
            "RegistrationStatus": {"$": "PUBLISHED"},
        },
    }
}


def _build_fixture_index(path: Path) -> None:
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE lei_entities ("
        "  lei TEXT PRIMARY KEY,"
        "  legal_name TEXT,"
        "  legal_jurisdiction TEXT,"
        "  entity_status TEXT,"
        "  registration_status TEXT"
        ")"
    )
    conn.executemany(
        "INSERT INTO lei_entities (lei, legal_name, legal_jurisdiction, entity_status, registration_status) "
        "VALUES (?, ?, ?, 'ACTIVE', 'ISSUED')",
        [
            (DOKOBIT_LEI, DOKOBIT_NAME, DOKOBIT_JURISDICTION),
            (SIGNICAT_LEI, SIGNICAT_NAME, SIGNICAT_JURISDICTION),
        ],
    )
    conn.commit()
    conn.close()


def test_gleif_lei_index_importable_from_providers():
    # The bug: this import raised ModuleNotFoundError before the fix,
    # unconditionally, regardless of any data or logic question.
    assert GleifLeiIndex is not None


def test_auto_enrichment_resolves_real_leis_without_manual_overrides(tmp_path):
    db_path = tmp_path / "gleif_lei_fixture.sqlite"
    _build_fixture_index(db_path)

    with GleifLeiIndex(db_path) as idx:
        out = GleifRelationshipRecordAdapter().from_record(
            RAW_RECORD, names={}, jurisdictions={}, lei_index=idx
        ).to_dict()

    assert out["entities"][0]["legal_name"] == SIGNICAT_NAME
    assert out["entities"][0]["jurisdiction"] == SIGNICAT_JURISDICTION
    assert out["metadata"]["resolution_status"] == RESOLVED
    assert out["relationships"][0]["attributes"]["child_resolution_status"] == RESOLVED
    assert out["relationships"][0]["attributes"]["parent_resolution_status"] == RESOLVED
    assert out["warnings"] == []


def test_auto_enrichment_matches_manual_override_baseline(tmp_path):
    # The whole point of M4.2: the auto-enriched result should be
    # equivalent to what used to require hand-supplied --name/--jurisdiction
    # flags, for an LEI that's actually in the index.
    db_path = tmp_path / "gleif_lei_fixture.sqlite"
    _build_fixture_index(db_path)

    manual = GleifRelationshipRecordAdapter().from_record(
        RAW_RECORD,
        names={DOKOBIT_LEI: DOKOBIT_NAME, SIGNICAT_LEI: SIGNICAT_NAME},
        jurisdictions={DOKOBIT_LEI: DOKOBIT_JURISDICTION, SIGNICAT_LEI: SIGNICAT_JURISDICTION},
        lei_index=None,
    ).to_dict()

    with GleifLeiIndex(db_path) as idx:
        auto = GleifRelationshipRecordAdapter().from_record(
            RAW_RECORD, names={}, jurisdictions={}, lei_index=idx
        ).to_dict()

    assert manual["entities"][0]["legal_name"] == auto["entities"][0]["legal_name"]
    assert manual["entities"][0]["jurisdiction"] == auto["entities"][0]["jurisdiction"]
    assert manual["relationships"][0]["predicate"] == auto["relationships"][0]["predicate"]


def test_lei_not_in_index_is_unresolved_retry_not_invented(tmp_path):
    db_path = tmp_path / "gleif_lei_fixture.sqlite"
    _build_fixture_index(db_path)

    unknown_record = {
        "RelationshipRecord": {
            "Relationship": {
                "StartNode": {"NodeID": {"$": "UNKNOWNLEI0000000001"}},
                "EndNode": {"NodeID": {"$": SIGNICAT_LEI}},
                "RelationshipType": {"$": "IS_DIRECTLY_CONSOLIDATED_BY"},
                "RelationshipStatus": {"$": "ACTIVE"},
            },
            "Registration": {
                "LastUpdateDate": {"$": "2026-09-25T00:00:00Z"},
                "RegistrationStatus": {"$": "PUBLISHED"},
            },
        }
    }

    with GleifLeiIndex(db_path) as idx:
        out = GleifRelationshipRecordAdapter().from_record(
            unknown_record, names={}, jurisdictions={}, lei_index=idx
        ).to_dict()

    assert out["metadata"]["resolution_status"] == UNRESOLVED_RETRY
    # Never invent a name for an unresolved LEI -- the bare LEI stays
    # visible as the display value.
    assert out["resolved_name"] == "UNKNOWNLEI0000000001"
