"""The queried legal entity must not be confused with an ownership graph root."""
from pathlib import Path
import sqlite3
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))
from identity_lookup import legal_name_lookup_key
from root_entity_resolver import resolve_company_root


def databases(tmp_path):
    lei = tmp_path / "lei.sqlite"
    rr = tmp_path / "rr.sqlite"
    with sqlite3.connect(lei) as conn:
        conn.execute("""
            CREATE TABLE lei_entities (
                lei TEXT PRIMARY KEY,
                legal_name TEXT,
                legal_name_lookup_key TEXT,
                legal_jurisdiction TEXT,
                entity_status TEXT,
                entity_category TEXT,
                registration_status TEXT
            )
        """)
    with sqlite3.connect(rr) as conn:
        conn.execute("""
            CREATE TABLE relationships (
                child_lei TEXT, parent_lei TEXT,
                relationship_type TEXT, relationship_status TEXT
            )
        """)
    return lei, rr


def add(lei_path, lei, name, status="ACTIVE", category="GENERAL"):
    with sqlite3.connect(lei_path) as conn:
        conn.execute(
            "INSERT INTO lei_entities VALUES (?, ?, ?, 'US-DE', ?, ?, 'ISSUED')",
            (lei, name, legal_name_lookup_key(name), status, category),
        )


def parent(rr_path, child, root):
    with sqlite3.connect(rr_path) as conn:
        conn.execute(
            "INSERT INTO relationships VALUES (?, ?, 'IS_ULTIMATELY_CONSOLIDATED_BY', 'ACTIVE')",
            (child, root),
        )


def test_exact_child_identity_is_preserved_when_parent_outscores_it(tmp_path):
    lei, rr = databases(tmp_path)
    add(lei, "CHILD", "CITRIX SYSTEMS, INC.")
    add(lei, "PARENT", "Cloud Software Group, LLC")
    parent(rr, "CHILD", "PARENT")
    result = resolve_company_root("Citrix Systems Inc", str(lei), str(rr)).to_dict()
    assert result["root"]["lei"] == "PARENT"
    assert result["status"] == "REVIEW_REQUIRED"
    identity = result["queried_identity"]
    assert identity["status"] == "UNIQUE_ACTIVE_EXACT_NAME"
    assert identity["entity"]["lei"] == "CHILD"
    assert identity["evidence_level"] == "GLEIF_LEGAL_NAME_MATCH_ONLY"


def test_duplicate_exact_legal_name_is_ambiguous_even_if_one_is_branch(tmp_path):
    lei, rr = databases(tmp_path)
    add(lei, "BRANCH", "THE TIMKEN COMPANY", category="BRANCH")
    add(lei, "GENERAL", "THE TIMKEN COMPANY")
    result = resolve_company_root("The Timken Company", str(lei), str(rr)).to_dict()
    identity = result["queried_identity"]
    assert identity["status"] == "AMBIGUOUS_EXACT_NAME"
    assert identity["entity"] is None
    assert {x["lei"] for x in identity["exact_name_matches"]} == {"BRANCH", "GENERAL"}


def test_inactive_exact_name_kept_for_review(tmp_path):
    lei, rr = databases(tmp_path)
    add(lei, "AKORN", "Akorn, Inc.", status="INACTIVE")
    result = resolve_company_root("Akorn Inc.", str(lei), str(rr)).to_dict()
    identity = result["queried_identity"]
    assert identity["status"] == "INACTIVE_EXACT_NAME"
    assert identity["entity"] is None
    assert identity["exact_name_matches"][0]["lei"] == "AKORN"


def test_partial_name_does_not_inherit_exact_identity(tmp_path):
    lei, rr = databases(tmp_path)
    add(lei, "TRADING", "SEMPRA ENERGY TRADING LLC")
    add(lei, "NATWEST", "NATWEST GROUP PLC")
    parent(rr, "TRADING", "NATWEST")
    result = resolve_company_root("Sempra Energy", str(lei), str(rr)).to_dict()
    assert result["queried_identity"]["status"] == "NO_EXACT_NAME_MATCH"
    assert result["queried_identity"]["entity"] is None


def test_unique_active_exact_name_without_parent(tmp_path):
    lei, rr = databases(tmp_path)
    add(lei, "TARGET", "Target Corporation")
    result = resolve_company_root("Target Corporation", str(lei), str(rr)).to_dict()
    assert result["queried_identity"]["entity"]["lei"] == "TARGET"
    assert result["status"] == "AUTO_RESOLVED"
