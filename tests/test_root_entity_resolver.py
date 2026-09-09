#!/usr/bin/env python3
from __future__ import annotations

import sqlite3
import tempfile
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))

from root_entity_resolver import (
    _contains_token_phrase,
    find_seed_matches,
    resolve_company_root,
)


def make_dbs(tmp: Path):
    lei = tmp / "lei.sqlite"
    rr = tmp / "rr.sqlite"

    lc = sqlite3.connect(lei)
    lc.row_factory = sqlite3.Row
    lc.executescript(
        """
        CREATE TABLE lei_entities (
            lei TEXT PRIMARY KEY,
            legal_name TEXT,
            legal_name_normalized TEXT,
            legal_jurisdiction TEXT,
            entity_status TEXT
        );
        """
    )

    rc = sqlite3.connect(rr)
    rc.row_factory = sqlite3.Row
    rc.executescript(
        """
        CREATE TABLE relationships (
            child_lei TEXT,
            parent_lei TEXT,
            relationship_type TEXT,
            relationship_status TEXT
        );
        """
    )
    return lei, rr, lc, rc


def add_entity(conn, lei, name, jurisdiction="US", status="ACTIVE"):
    conn.execute(
        """
        INSERT INTO lei_entities
        (lei, legal_name, legal_name_normalized, legal_jurisdiction, entity_status)
        VALUES (?, ?, ?, ?, ?)
        """,
        (lei, name, name.casefold(), jurisdiction, status),
    )


def add_rel(conn, child, parent, rel_type):
    conn.execute(
        """
        INSERT INTO relationships
        (child_lei, parent_lei, relationship_type, relationship_status)
        VALUES (?, ?, ?, 'ACTIVE')
        """,
        (child, parent, rel_type),
    )


def test_acronym_token_matching_rejects_substrings():
    assert _contains_token_phrase("NTT", "NTT DATA EUROPE LIMITED")
    assert _contains_token_phrase("NTT", "ABC NTT Holdings")
    assert not _contains_token_phrase("NTT", "AINOA Anttila Oy")
    assert not _contains_token_phrase("NTT", "Planttech Engineering GmbH")
    assert not _contains_token_phrase("NTT", "ADVANTTE VENTURE PARTNERS SL")
    print("PASS test_acronym_token_matching_rejects_substrings")


def test_seed_filter_removes_ntt_false_positives():
    with tempfile.TemporaryDirectory() as d:
        lei, rr, lc, rc = make_dbs(Path(d))
        add_entity(lc, "A", "NTT DATA ALPHA")
        add_entity(lc, "B", "Planttech Engineering GmbH")
        add_entity(lc, "C", "AINOA Anttila Oy")
        lc.commit()
        rows = find_seed_matches(lc, "NTT")
        lc.close(); rc.close()
        assert [r["lei"] for r in rows] == ["A"]
        print("PASS test_seed_filter_removes_ntt_false_positives")


def test_multiple_matches_converge_on_common_root():
    with tempfile.TemporaryDirectory() as d:
        lei, rr, lc, rc = make_dbs(Path(d))
        add_entity(lc, "A", "NTT DATA ALPHA")
        add_entity(lc, "B", "NTT DATA BETA")
        add_entity(lc, "R", "NIPPON TELEGRAPH AND TELEPHONE CORPORATION", "JP")
        add_rel(rc, "A", "R", "IS_ULTIMATELY_CONSOLIDATED_BY")
        add_rel(rc, "B", "R", "IS_ULTIMATELY_CONSOLIDATED_BY")
        lc.commit(); rc.commit(); lc.close(); rc.close()

        result = resolve_company_root("NTT", str(lei), str(rr))
        assert result.status == "AUTO_RESOLVED"
        assert result.confidence == "HIGH"
        assert result.root.lei == "R"
        print("PASS test_multiple_matches_converge_on_common_root")


def test_split_families_require_review():
    with tempfile.TemporaryDirectory() as d:
        lei, rr, lc, rc = make_dbs(Path(d))
        add_entity(lc, "A", "NTT ALPHA")
        add_entity(lc, "B", "NTT BETA")
        add_entity(lc, "R1", "ROOT ONE")
        add_entity(lc, "R2", "ROOT TWO")
        add_rel(rc, "A", "R1", "IS_ULTIMATELY_CONSOLIDATED_BY")
        add_rel(rc, "B", "R2", "IS_ULTIMATELY_CONSOLIDATED_BY")
        lc.commit(); rc.commit(); lc.close(); rc.close()

        result = resolve_company_root("NTT", str(lei), str(rr))
        assert result.status == "REVIEW_REQUIRED"
        print("PASS test_split_families_require_review")


def test_unique_exact_active_can_resolve_without_relationships():
    with tempfile.TemporaryDirectory() as d:
        lei, rr, lc, rc = make_dbs(Path(d))
        add_entity(lc, "X", "Acme")
        lc.commit(); rc.commit(); lc.close(); rc.close()

        result = resolve_company_root("Acme", str(lei), str(rr))
        assert result.status == "AUTO_RESOLVED"
        assert result.root.lei == "X"
        print("PASS test_unique_exact_active_can_resolve_without_relationships")


def test_no_match():
    with tempfile.TemporaryDirectory() as d:
        lei, rr, lc, rc = make_dbs(Path(d))
        add_entity(lc, "X", "Acme")
        lc.commit(); rc.commit(); lc.close(); rc.close()

        result = resolve_company_root("NTT", str(lei), str(rr))
        assert result.status == "NO_MATCH"
        print("PASS test_no_match")


def test_cycle_is_bounded():
    with tempfile.TemporaryDirectory() as d:
        lei, rr, lc, rc = make_dbs(Path(d))
        add_entity(lc, "A", "NTT A")
        add_entity(lc, "B", "NTT B")
        add_rel(rc, "A", "B", "IS_DIRECTLY_CONSOLIDATED_BY")
        add_rel(rc, "B", "A", "IS_DIRECTLY_CONSOLIDATED_BY")
        lc.commit(); rc.commit(); lc.close(); rc.close()

        result = resolve_company_root("NTT", str(lei), str(rr), max_depth=4)
        assert len(result.candidates) <= 2
        print("PASS test_cycle_is_bounded")


def test_isolated_lexical_matches_do_not_dilute_real_convergence():
    with tempfile.TemporaryDirectory() as d:
        lei, rr, lc, rc = make_dbs(Path(d))

        # Three genuine family members converge on one root.
        add_entity(lc, "A", "SONY ALPHA")
        add_entity(lc, "B", "SONY BETA")
        add_entity(lc, "C", "SONY GAMMA")
        add_entity(lc, "R", "ソニーグループ株式会社", "JP")
        add_rel(rc, "A", "R", "IS_ULTIMATELY_CONSOLIDATED_BY")
        add_rel(rc, "B", "R", "IS_ULTIMATELY_CONSOLIDATED_BY")
        add_rel(rc, "C", "R", "IS_ULTIMATELY_CONSOLIDATED_BY")

        # Many token-valid but topology-free names must not count as votes
        # against the actual corporate family.
        for i in range(20):
            add_entity(lc, f"J{i}", f"SONY unrelated {i}")

        lc.commit(); rc.commit(); lc.close(); rc.close()

        result = resolve_company_root("Sony", str(lei), str(rr))
        assert result.status == "AUTO_RESOLVED"
        assert result.confidence == "HIGH"
        assert result.root.lei == "R"
        assert result.root.matched_seed_count == 3
        assert result.root.total_seed_count == 3
        assert result.root.coverage == 1.0
        print("PASS test_isolated_lexical_matches_do_not_dilute_real_convergence")


def test_competing_informative_families_still_require_review():
    with tempfile.TemporaryDirectory() as d:
        lei, rr, lc, rc = make_dbs(Path(d))

        add_entity(lc, "A1", "SONY ALPHA")
        add_entity(lc, "A2", "SONY BETA")
        add_entity(lc, "B1", "SONY GAMMA")
        add_entity(lc, "B2", "SONY DELTA")
        add_entity(lc, "R1", "ROOT ONE")
        add_entity(lc, "R2", "ROOT TWO")

        add_rel(rc, "A1", "R1", "IS_ULTIMATELY_CONSOLIDATED_BY")
        add_rel(rc, "A2", "R1", "IS_ULTIMATELY_CONSOLIDATED_BY")
        add_rel(rc, "B1", "R2", "IS_ULTIMATELY_CONSOLIDATED_BY")
        add_rel(rc, "B2", "R2", "IS_ULTIMATELY_CONSOLIDATED_BY")

        lc.commit(); rc.commit(); lc.close(); rc.close()

        result = resolve_company_root("Sony", str(lei), str(rr))
        assert result.status == "REVIEW_REQUIRED"
        print("PASS test_competing_informative_families_still_require_review")


if __name__ == "__main__":
    suite = [
        test_acronym_token_matching_rejects_substrings,
        test_seed_filter_removes_ntt_false_positives,
        test_multiple_matches_converge_on_common_root,
        test_split_families_require_review,
        test_unique_exact_active_can_resolve_without_relationships,
        test_no_match,
        test_cycle_is_bounded,
        test_isolated_lexical_matches_do_not_dilute_real_convergence,
        test_competing_informative_families_still_require_review,
    ]

    failed = 0
    for test in suite:
        try:
            test()
        except Exception as exc:
            failed += 1
            print(f"FAIL {test.__name__}: {exc}")

    print(f"{len(suite)-failed} passed / {failed} failed")
    raise SystemExit(1 if failed else 0)
