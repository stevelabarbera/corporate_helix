#!/usr/bin/env python3
"""Alias fallback: discover identity leads, never auto-assert ownership."""
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))
from root_entity_resolver import resolve_company_root


class AliasFallbackTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.lei, self.rr, self.alias = (root / x for x in ("lei.db", "rr.db", "alias.db"))
        with sqlite3.connect(self.lei) as db:
            db.executescript("""
                CREATE TABLE lei_entities (
                    lei TEXT PRIMARY KEY, legal_name TEXT,
                    legal_name_normalized TEXT, legal_jurisdiction TEXT,
                    entity_status TEXT);
            """)
            db.executemany("INSERT INTO lei_entities VALUES (?,?,?,?,?)", [
                ("X", "New Organization Ltd", "new organization ltd", "GB", "ACTIVE"),
                ("Y", "Different Organization Ltd", "different organization ltd", "US", "ACTIVE"),
            ])
        with sqlite3.connect(self.rr) as db:
            db.executescript("""
                CREATE TABLE relationships (
                    child_lei TEXT, parent_lei TEXT,
                    relationship_type TEXT, relationship_status TEXT);
            """)
        with sqlite3.connect(self.alias) as db:
            db.executescript("""
                CREATE TABLE source_snapshot (source_level TEXT, is_sample INTEGER);
                CREATE TABLE source_observation (
                    observation_id INTEGER PRIMARY KEY,
                    record_identifier TEXT, source_ordinal INTEGER);
                CREATE TABLE entity_name (
                    observation_id INTEGER,
                    source_path TEXT,
                    source_ordinal INTEGER,
                    name TEXT,
                    name_normalized TEXT,
                    raw_value_json TEXT,
                    PRIMARY KEY(observation_id, source_path, source_ordinal));
            """)
            db.execute("INSERT INTO source_snapshot VALUES ('lei',0)")
            db.executemany("INSERT INTO source_observation VALUES (?,?,?)", [
                (1, "X", 9), (2, "Y", 10)
            ])

    def tearDown(self):
        self.tmp.cleanup()

    def alias_row(self, identifier, name, path="Entity.OtherEntityNames.OtherEntityName"):
        with sqlite3.connect(self.alias) as db:
            db.execute(
                """INSERT INTO entity_name
                   (observation_id, source_path, source_ordinal,
                    name, name_normalized, raw_value_json)
                   VALUES (?,?,?,?,?,?)""",
                (identifier, path, 0, name, name.casefold(),
                 json.dumps({"$": name, "@type": "PREVIOUS_LEGAL_NAME"})),
            )

    def test_exact_historical_name_is_review_only(self):
        self.alias_row(1, "Old Organization Ltd")
        result = resolve_company_root(
            "Old Organization Ltd", str(self.lei), str(self.rr), alias_db=str(self.alias))
        self.assertEqual(result.status, "REVIEW_REQUIRED")
        self.assertEqual(result.confidence, "LOW")
        self.assertEqual(result.root.lei, "X")
        self.assertEqual(result.seed_matches[0]["match_source"], "GLEIF_LEVEL1_ALIAS")
        self.assertEqual(result.seed_matches[0]["alias_source_record_ordinal"], 9)

    def test_duplicate_alias_entities_remain_ambiguous(self):
        self.alias_row(1, "Legacy Brand")
        self.alias_row(2, "Legacy Brand")
        result = resolve_company_root("Legacy Brand", str(self.lei), str(self.rr),
                                      alias_db=str(self.alias))
        self.assertEqual(result.status, "REVIEW_REQUIRED")
        self.assertEqual({x["lei"] for x in result.seed_matches}, {"X", "Y"})

    def test_canonical_identity_decision_is_unchanged(self):
        self.alias_row(2, "New Organization Ltd")
        result = resolve_company_root("New Organization Ltd", str(self.lei), str(self.rr),
                                      alias_db=str(self.alias))
        self.assertEqual(result.status, "AUTO_RESOLVED")
        self.assertEqual(result.root.lei, "X")
        self.assertNotIn("match_source", result.seed_matches[0])

    def test_incomplete_sample_is_rejected(self):
        self.alias_row(1, "Legacy Brand")
        with sqlite3.connect(self.alias) as db:
            db.execute("UPDATE source_snapshot SET is_sample=1")
        with self.assertRaisesRegex(ValueError, "complete Level 1 snapshot"):
            resolve_company_root("Legacy Brand", str(self.lei), str(self.rr),
                                 alias_db=str(self.alias))

    def test_sample_opt_in_never_autoresolves_and_no_match_is_inconclusive(self):
        self.alias_row(1, "Legacy Brand")
        with sqlite3.connect(self.alias) as db:
            db.execute("UPDATE source_snapshot SET is_sample=1")
        result = resolve_company_root("Legacy Brand", str(self.lei), str(self.rr),
                                      alias_db=str(self.alias), allow_sample_aliases=True)
        self.assertEqual(result.status, "REVIEW_REQUIRED")
        absent = resolve_company_root("Unseen Brand", str(self.lei), str(self.rr),
                                      alias_db=str(self.alias), allow_sample_aliases=True)
        self.assertEqual(absent.status, "INSUFFICIENT_EVIDENCE")

    def test_token_substrings_rejected(self):
        self.alias_row(1, "Planttechnology Labs")
        result = resolve_company_root("NTT", str(self.lei), str(self.rr),
                                      alias_db=str(self.alias))
        self.assertEqual(result.status, "NO_MATCH")


if __name__ == "__main__":
    unittest.main()
