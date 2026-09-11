#!/usr/bin/env python3
from __future__ import annotations

import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))

from providers.gleif_identity_fallback_provider import GleifIdentityFallbackProvider
from iterative_expansion import HelixFact


def _make_dbs(tmp: Path, entities: list[tuple]) -> tuple[str, str]:
    lei_path, rr_path = tmp / "lei.sqlite", tmp / "rr.sqlite"
    lc = sqlite3.connect(lei_path)
    lc.executescript(
        "CREATE TABLE lei_entities (lei TEXT PRIMARY KEY, legal_name TEXT, "
        "legal_name_normalized TEXT, legal_jurisdiction TEXT, entity_status TEXT);"
    )
    lc.executemany("INSERT INTO lei_entities VALUES (?,?,?,?,?)", entities)
    lc.commit(); lc.close()

    rc = sqlite3.connect(rr_path)
    rc.executescript(
        "CREATE TABLE relationships (child_lei TEXT, parent_lei TEXT, "
        "relationship_type TEXT, relationship_status TEXT);"
    )
    rc.commit(); rc.close()
    return str(lei_path), str(rr_path)


def _pivot(name: str, identifier: str | None = None) -> HelixFact:
    return HelixFact(
        fact_type="LEGAL_ENTITY", value=name, identifier=identifier,
        source="EDGAR_MA", confidence="HIGH", status="ACCEPTED", pivot_eligible=True,
    )


def test_resolves_identity_for_a_pivot_with_no_lei_yet():
    with tempfile.TemporaryDirectory() as d:
        lei, rr = _make_dbs(Path(d), [("LEI-ACME", "Acme Telemetry, Inc.", "acme telemetry inc", "US", "ACTIVE")])
        provider = GleifIdentityFallbackProvider(lei, rr)
        facts = list(provider(_pivot("Acme Telemetry, Inc."), 1))
        assert len(facts) == 1
        assert facts[0].identifier == "LEI-ACME"
        assert facts[0].source == "GLEIF_IDENTITY_FALLBACK"


def test_skips_pivots_that_already_have_an_lei():
    with tempfile.TemporaryDirectory() as d:
        lei, rr = _make_dbs(Path(d), [("LEI-ACME", "Acme Telemetry, Inc.", "acme telemetry inc", "US", "ACTIVE")])
        provider = GleifIdentityFallbackProvider(lei, rr)
        facts = list(provider(_pivot("Acme Telemetry, Inc.", identifier="LEI-ACME"), 1))
        assert facts == []


def test_no_match_produces_no_fact():
    with tempfile.TemporaryDirectory() as d:
        lei, rr = _make_dbs(Path(d), [("LEI-X", "Totally Different Corp.", "totally different corp", "US", "ACTIVE")])
        provider = GleifIdentityFallbackProvider(lei, rr)
        facts = list(provider(_pivot("Acme Telemetry, Inc."), 1))
        assert facts == []


def test_ambiguous_match_requiring_review_produces_no_fact():
    # Two similarly-named, unrelated entities -- root_entity_resolver should
    # correctly refuse to guess, and this provider must not override that by
    # picking one anyway.
    with tempfile.TemporaryDirectory() as d:
        lei, rr = _make_dbs(Path(d), [
            ("LEI-A", "Acme Telemetry Ltd", "acme telemetry ltd", "GB", "ACTIVE"),
            ("LEI-B", "Acme Telemetry Corp", "acme telemetry corp", "US", "ACTIVE"),
        ])
        provider = GleifIdentityFallbackProvider(lei, rr)
        facts = list(provider(_pivot("Acme Telemetry"), 1))
        assert facts == []


def test_ignores_fact_types_outside_its_scope():
    with tempfile.TemporaryDirectory() as d:
        lei, rr = _make_dbs(Path(d), [("LEI-ACME", "Acme Telemetry, Inc.", "acme telemetry inc", "US", "ACTIVE")])
        provider = GleifIdentityFallbackProvider(lei, rr)
        domain_pivot = HelixFact(
            fact_type="DOMAIN", value="acme.example", identifier=None,
            source="X", confidence="HIGH", status="ACCEPTED", pivot_eligible=True,
        )
        assert list(provider(domain_pivot, 1)) == []
