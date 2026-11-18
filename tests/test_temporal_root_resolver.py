#!/usr/bin/env python3
"""Temporal eligibility tests for GLEIF current-snapshot root traversal."""
from __future__ import annotations

import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))

from root_entity_resolver import _parents_for, resolve_company_root


class TemporalRootTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        folder = Path(self.tmp.name)
        self.lei = folder / "lei.sqlite"
        self.rr = folder / "rr.sqlite"
        self.lc = sqlite3.connect(self.lei)
        self.rc = sqlite3.connect(self.rr)
        self.rc.row_factory = sqlite3.Row
        self.lc.executescript("""
            CREATE TABLE lei_entities (
                lei TEXT PRIMARY KEY, legal_name TEXT,
                legal_name_normalized TEXT, legal_jurisdiction TEXT,
                entity_status TEXT
            );
        """)
        self.rc.executescript("""
            CREATE TABLE relationships (
                child_lei TEXT, parent_lei TEXT,
                relationship_type TEXT, relationship_status TEXT,
                relationship_start TEXT, relationship_end TEXT,
                accounting_start TEXT, accounting_end TEXT
            );
        """)
        for lei, name in [("C", "Bolthouse Farms"), ("OLD", "Old Parent"),
                          ("NEW", "New Parent")]:
            self.lc.execute(
                "INSERT INTO lei_entities VALUES (?,?,?,?,?)",
                (lei, name, name.casefold(), "US", "ACTIVE"),
            )
        self.lc.commit()

    def tearDown(self):
        self.lc.close()
        self.rc.close()
        self.tmp.cleanup()

    def add(self, parent="OLD", status="ACTIVE", start=None, end=None,
            accounting_end=None):
        self.rc.execute(
            "INSERT INTO relationships VALUES (?,?,?,?,?,?,?,?)",
            ("C", parent, "IS_DIRECTLY_CONSOLIDATED_BY", status,
             start, end, "2024-01-01" if accounting_end else None,
             accounting_end),
        )
        self.rc.commit()

    def parents(self, day="2026-11-18"):
        return _parents_for(self.rc, "C", __import__("datetime").date.fromisoformat(day))

    def test_inactive_and_unknown_status_excluded(self):
        self.add(status="INACTIVE")
        self.add(parent="NEW", status=None)
        self.assertEqual(self.parents(), [])

    def test_expired_active_end_excluded(self):
        self.add(status="ACTIVE", start="2015-01-01", end="2019-12-31")
        self.assertEqual(self.parents(), [])

    def test_future_relationship_excluded(self):
        self.add(start="2027-01-01")
        self.assertEqual(self.parents(), [])
        self.assertEqual(len(self.parents("2027-01-01")), 1)

    def test_old_accounting_period_not_expiration(self):
        self.add(start="2019-01-01", accounting_end="2024-12-31")
        self.assertEqual(len(self.parents()), 1)

    def test_undated_active_provisionally_eligible(self):
        self.add()
        self.assertEqual(len(self.parents()), 1)

    def test_malformed_period_fails_closed(self):
        self.add(end="NOT_A_DATE")
        self.assertEqual(self.parents(), [])

    def test_resolver_does_not_follow_expired_old_parent(self):
        self.add("OLD", end="2019-12-31")
        self.add("NEW", start="2020-01-01")
        result = resolve_company_root(
            "Bolthouse Farms", str(self.lei), str(self.rr),
            as_of_date="2026-11-18",
        )
        self.assertNotIn("OLD", [c.lei for c in result.candidates])
        self.assertIn("NEW", [c.lei for c in result.candidates])

    def test_as_of_replays_period_not_historical_snapshot_status(self):
        self.add("OLD", start="2015-01-01", end="2019-12-31")
        self.add("NEW", start="2020-01-01")
        result = resolve_company_root(
            "Bolthouse Farms", str(self.lei), str(self.rr),
            as_of_date="2018-01-01",
        )
        self.assertIn("OLD", [c.lei for c in result.candidates])
        self.assertNotIn("NEW", [c.lei for c in result.candidates])

    def test_bad_as_of_rejected(self):
        self.add()
        with self.assertRaises(ValueError):
            resolve_company_root("Bolthouse Farms", str(self.lei), str(self.rr),
                                 as_of_date="November 2026")


if __name__ == "__main__":
    unittest.main()
