#!/usr/bin/env python3
from __future__ import annotations

import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CLI = REPO / "code" / "helix_company.py"


def make_dbs(tmp: Path):
    lei = tmp / "lei.sqlite"
    rr = tmp / "rr.sqlite"

    lc = sqlite3.connect(lei)
    lc.executescript(
        '''
        CREATE TABLE lei_entities (
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
        '''
    )

    rc = sqlite3.connect(rr)
    rc.executescript(
        '''
        CREATE TABLE relationships (
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
        '''
    )
    return lei, rr, lc, rc


def add_entity(conn, lei, name, jurisdiction="US", status="ACTIVE"):
    conn.execute(
        '''
        INSERT INTO lei_entities (
            lei, legal_name, legal_name_normalized,
            legal_jurisdiction, entity_status, registration_status
        )
        VALUES (?, ?, ?, ?, ?, 'ISSUED')
        ''',
        (lei, name, name.casefold(), jurisdiction, status),
    )


def add_rel(conn, child, parent, rel_type):
    conn.execute(
        '''
        INSERT INTO relationships (
            child_lei, parent_lei, relationship_type, relationship_status
        )
        VALUES (?, ?, ?, 'ACTIVE')
        ''',
        (child, parent, rel_type),
    )


def run_cli(lei, rr, *extra):
    return subprocess.run(
        [
            sys.executable,
            str(CLI),
            *extra,
            "--lei-index", str(lei),
            "--rr-index", str(rr),
        ],
        cwd=REPO,
        text=True,
        capture_output=True,
    )


def test_company_only_resolves_then_expands():
    with tempfile.TemporaryDirectory() as d:
        lei, rr, lc, rc = make_dbs(Path(d))
        add_entity(lc, "A", "NTT DATA ALPHA")
        add_entity(lc, "B", "NTT DATA BETA")
        add_entity(lc, "R", "ROOT CORPORATION", "JP")
        add_rel(rc, "A", "R", "IS_ULTIMATELY_CONSOLIDATED_BY")
        add_rel(rc, "B", "R", "IS_ULTIMATELY_CONSOLIDATED_BY")
        lc.commit(); rc.commit(); lc.close(); rc.close()

        p = run_cli(lei, rr, "--company", "NTT")
        assert p.returncode == 0, p.stdout + p.stderr
        assert "ROOT CORPORATION" in p.stdout
        assert "LEI          : R" in p.stdout
        assert "NTT DATA ALPHA" in p.stdout
        assert "NTT DATA BETA" in p.stdout
        print("PASS test_company_only_resolves_then_expands")


def test_explicit_lei_override_still_works():
    with tempfile.TemporaryDirectory() as d:
        lei, rr, lc, rc = make_dbs(Path(d))
        add_entity(lc, "X", "MANUAL ROOT")
        lc.commit(); rc.commit(); lc.close(); rc.close()

        p = run_cli(lei, rr, "--company", "Anything", "--lei", "X")
        assert p.returncode == 0, p.stdout + p.stderr
        assert "MANUAL ROOT" in p.stdout
        assert "LEI          : X" in p.stdout
        print("PASS test_explicit_lei_override_still_works")


def test_ambiguous_graph_refuses_auto_selection():
    with tempfile.TemporaryDirectory() as d:
        lei, rr, lc, rc = make_dbs(Path(d))
        add_entity(lc, "A", "NTT ALPHA")
        add_entity(lc, "B", "NTT BETA")
        add_entity(lc, "R1", "ROOT ONE")
        add_entity(lc, "R2", "ROOT TWO")
        add_rel(rc, "A", "R1", "IS_ULTIMATELY_CONSOLIDATED_BY")
        add_rel(rc, "B", "R2", "IS_ULTIMATELY_CONSOLIDATED_BY")
        lc.commit(); rc.commit(); lc.close(); rc.close()

        p = run_cli(lei, rr, "--company", "NTT")
        assert p.returncode == 2
        assert "REVIEW_REQUIRED" in p.stdout
        assert "Root identity was not safe to select automatically." in p.stdout
        print("PASS test_ambiguous_graph_refuses_auto_selection")


if __name__ == "__main__":
    suite = [
        test_company_only_resolves_then_expands,
        test_explicit_lei_override_still_works,
        test_ambiguous_graph_refuses_auto_selection,
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
