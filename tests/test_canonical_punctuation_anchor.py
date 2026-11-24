#!/usr/bin/env python3
"""Canonical exact-name retrieval must match the legacy GLEIF index format."""
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))
from root_entity_resolver import find_seed_matches, normalize_name, resolve_company_root


class CanonicalPunctuationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        base = Path(self.temp.name)
        self.lei = base / "lei.sqlite"
        self.rr = base / "rr.sqlite"
        with sqlite3.connect(self.lei) as conn:
            conn.executescript("""
                CREATE TABLE lei_entities (
                    lei TEXT PRIMARY KEY,
                    legal_name TEXT,
                    legal_name_normalized TEXT,
                    legal_jurisdiction TEXT,
                    entity_status TEXT
                );
            """)
        with sqlite3.connect(self.rr) as conn:
            conn.executescript("""
                CREATE TABLE relationships (
                    child_lei TEXT,
                    parent_lei TEXT,
                    relationship_type TEXT,
                    relationship_status TEXT,
                    relationship_start TEXT,
                    relationship_end TEXT
                );
            """)

    def tearDown(self):
        self.temp.cleanup()

    def add_entity(self, lei, name):
        with sqlite3.connect(self.lei) as conn:
            conn.execute(
                "INSERT INTO lei_entities VALUES(?, ?, ?, 'US', 'ACTIVE')",
                (lei, name, name.casefold()),
            )

    def read_seeds(self, query):
        with sqlite3.connect(self.lei) as conn:
            conn.row_factory = sqlite3.Row
            return find_seed_matches(conn, query)

    def test_exact_ampersand_is_canonical_seed_and_approved_identity(self):
        self.add_entity("JJ", "Johnson & Johnson")
        self.add_entity("ETF", "Johnson & Johnson Yield Shares ETF")
        rows = self.read_seeds("Johnson & Johnson")
        self.assertEqual([r["lei"] for r in rows], ["JJ"])
        result = resolve_company_root("Johnson & Johnson", str(self.lei), str(self.rr))
        self.assertEqual(result.status, "AUTO_RESOLVED")
        self.assertIsNotNone(result.root)
        self.assertEqual(result.root.lei, "JJ")

    def test_stripping_punctuation_does_not_create_false_anchor(self):
        self.add_entity("JJ", "Johnson & Johnson")
        result = resolve_company_root("Johnson Johnson", str(self.lei), str(self.rr))
        # This punctuation-normalized name is the SAME complete token name,
        # so it is allowed as a canonical identity only after the full name
        # has been retrieved and checked. This test documents the semantics.
        self.assertEqual(result.status, "REVIEW_REQUIRED")
        self.assertIsNone(result.root)

    def test_ambiguous_exact_canonicals_still_require_review(self):
        self.add_entity("A", "Johnson & Johnson")
        self.add_entity("B", "JOHNSON & JOHNSON")
        result = resolve_company_root("Johnson & Johnson", str(self.lei), str(self.rr))
        self.assertEqual(result.status, "REVIEW_REQUIRED")
        self.assertIsNone(result.root)
        self.assertEqual({s["lei"] for s in result.seed_matches}, {"A", "B"})

    def test_partial_names_not_approved(self):
        self.add_entity("JJ", "Johnson & Johnson")
        result = resolve_company_root("Johnson", str(self.lei), str(self.rr))
        self.assertEqual(result.status, "REVIEW_REQUIRED")
        self.assertIsNone(result.root)


if __name__ == "__main__":
    unittest.main()
