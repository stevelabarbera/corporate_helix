#!/usr/bin/env python3
"""Identity anchoring: query-to-seed evidence must precede parent endorsement."""
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))
from root_entity_resolver import resolve_company_root


class IdentityAnchorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.lei, self.rr = root / "lei.sqlite", root / "rr.sqlite"
        with sqlite3.connect(self.lei) as db:
            db.executescript("""
                CREATE TABLE lei_entities (
                    lei TEXT PRIMARY KEY, legal_name TEXT,
                    legal_name_normalized TEXT, legal_jurisdiction TEXT,
                    entity_status TEXT);
            """)
        with sqlite3.connect(self.rr) as db:
            db.executescript("""
                CREATE TABLE relationships (
                    child_lei TEXT, parent_lei TEXT, relationship_type TEXT,
                    relationship_status TEXT);
            """)

    def tearDown(self):
        self.tmp.cleanup()

    def entity(self, lei, name, status="ACTIVE"):
        with sqlite3.connect(self.lei) as db:
            db.execute("INSERT INTO lei_entities VALUES(?,?,?,?,?)",
                       (lei, name, name.casefold(), "US", status))

    def parent(self, child, parent):
        with sqlite3.connect(self.rr) as db:
            db.execute("INSERT INTO relationships VALUES(?,?,?,?)",
                       (child, parent, "IS_ULTIMATELY_CONSOLIDATED_BY", "ACTIVE"))

    def resolve(self, query):
        return resolve_company_root(query, str(self.lei), str(self.rr))

    def test_sempra_wrong_parent_is_only_exploratory(self):
        self.entity("TRADE", "SEMPRA ENERGY TRADING LLC")
        self.entity("NAT", "NATWEST GROUP PLC")
        self.parent("TRADE", "NAT")
        result = self.resolve("Sempra Energy")
        self.assertEqual(result.status, "REVIEW_REQUIRED")
        self.assertIsNone(result.root)
        self.assertEqual(result.candidates[0].lei, "NAT")
        self.assertEqual(result.seed_matches[0]["lei"], "TRADE")
        self.assertIn("No exact canonical", result.reason)

    def test_regional_subsidiary_is_not_corporate_root(self):
        self.entity("INDIA", "SENTINELONE CYBERSECURITY INDIA PRIVATE LIMITED")
        result = self.resolve("SentinelOne")
        self.assertEqual(result.status, "REVIEW_REQUIRED")
        self.assertIsNone(result.root)
        self.assertEqual(result.candidates[0].lei, "INDIA")

    def test_exact_seed_still_resolves_its_identity(self):
        self.entity("REAL", "SEMPRA ENERGY")
        result = self.resolve("Sempra Energy")
        self.assertEqual(result.status, "AUTO_RESOLVED")
        self.assertEqual(result.root.lei, "REAL")

    def test_exact_seed_not_overridden_by_unrelated_phrase_family(self):
        self.entity("REAL", "SEMPRA ENERGY")
        self.entity("TRADE", "SEMPRA ENERGY TRADING LLC")
        self.entity("NAT", "NATWEST GROUP PLC")
        self.parent("TRADE", "NAT")
        result = self.resolve("Sempra Energy")
        self.assertEqual(result.status, "REVIEW_REQUIRED")
        self.assertIsNone(result.root)
        self.assertIn("REAL", {s["lei"] for s in result.seed_matches})
        self.assertIn("NAT", {c.lei for c in result.candidates})

    def test_multiple_exact_legal_names_are_ambiguous(self):
        self.entity("A", "Acme Corp")
        self.entity("B", "ACME CORP")
        result = self.resolve("Acme Corp")
        self.assertEqual(result.status, "REVIEW_REQUIRED")
        self.assertIsNone(result.root)
        self.assertEqual({c.lei for c in result.candidates}, {"A", "B"})

    def test_inactive_exact_anchor_needs_review(self):
        self.entity("X", "Acme Corp", "INACTIVE")
        result = self.resolve("Acme Corp")
        self.assertEqual(result.status, "REVIEW_REQUIRED")
        self.assertIsNone(result.root)
        self.assertEqual(result.candidates[0].lei, "X")


if __name__ == "__main__":
    unittest.main()
