#!/usr/bin/env python3
"""Quality diagnostics must flag misleading roots without fabricating ground truth."""
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))
from audit_identity_quality import inspect_case, reconcile_alias_leis


class QualityGatesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        directory = Path(self.tmp.name)
        self.lei = directory / "lei.db"
        self.rr = directory / "rr.db"
        self.alias = directory / "alias.db"
        with sqlite3.connect(self.lei) as db:
            db.executescript("""
                CREATE TABLE lei_entities (
                    lei TEXT PRIMARY KEY, legal_name TEXT,
                    legal_name_normalized TEXT, legal_jurisdiction TEXT,
                    entity_status TEXT);
                INSERT INTO lei_entities VALUES
                  ('TRADING', 'SEMPRA ENERGY TRADING LLC', 'sempra energy trading llc','US','ACTIVE'),
                  ('NATWEST', 'NATWEST GROUP PLC','natwest group plc','GB','ACTIVE'),
                  ('REAL', 'SEMPRA ENERGY','sempra energy','US','ACTIVE');
            """)
        with sqlite3.connect(self.rr) as db:
            db.executescript("""
                CREATE TABLE relationships (
                  child_lei TEXT, parent_lei TEXT,
                  relationship_type TEXT, relationship_status TEXT);
                INSERT INTO relationships VALUES
                  ('TRADING','NATWEST','IS_ULTIMATELY_CONSOLIDATED_BY','ACTIVE');
            """)
        with sqlite3.connect(self.alias) as db:
            db.executescript("""
                CREATE TABLE source_snapshot(
                  source_level TEXT, source_archive_sha256 TEXT,
                  record_count INTEGER,alias_count INTEGER,is_sample INTEGER);
                INSERT INTO source_snapshot VALUES('lei','sha',3,2,0);
                CREATE TABLE source_observation(
                  observation_id INTEGER PRIMARY KEY,
                  source_ordinal INTEGER, record_identifier TEXT);
                INSERT INTO source_observation VALUES
                  (1,1,'TRADING'),(2,2,'GONE');
            """)

    def tearDown(self):
        self.tmp.cleanup()

    def test_flags_wrong_seed_root_without_claiming_accuracy(self):
        with sqlite3.connect(self.lei) as db:
            db.execute("DELETE FROM lei_entities WHERE lei='REAL'")
        result = inspect_case("Sempra Energy", str(self.lei), str(self.rr))
        self.assertIn("NO_EXACT_CANONICAL_NAME_IDENTITY_ANCHOR", result["quality_warnings"])
        self.assertIn("EXPLORATORY_ROOT_LACKS_VERIFIED_QUERY_IDENTITY", result["quality_warnings"])
        self.assertIsNone(result["proposed_root"])
        self.assertEqual(result["exploratory_top_candidate"]["legal_name"], "NATWEST GROUP PLC")
        self.assertFalse(result["ownership_verified"])
        self.assertEqual(result["proposed_root_correctness"], "NOT_SCORED")
        self.assertIn("TRADING", [s["lei"] for s in result["seed_evidence"]])

    def test_exact_anchor_does_not_make_relationship_owned(self):
        result = inspect_case("Sempra Energy", str(self.lei), str(self.rr))
        self.assertTrue(any(s["exact_query_name"] for s in result["seed_evidence"]))
        self.assertFalse(result["ownership_verified"])
        self.assertEqual(result["identity_correctness"], "NOT_SCORED")

    def test_reconciliation_counts_missing(self):
        coverage = reconcile_alias_leis(str(self.lei), str(self.alias))
        self.assertEqual(coverage["alias_bearing_entities"], 2)
        self.assertEqual(coverage["present_in_canonical_index"], 1)
        self.assertEqual(coverage["missing_in_canonical_index"], 1)
        self.assertEqual(coverage["missing_examples"][0]["lei"], "GONE")
        self.assertFalse(coverage["snapshot_identity_verified"])

    def test_sample_refused_for_population_reconciliation(self):
        with sqlite3.connect(self.alias) as db:
            db.execute("UPDATE source_snapshot SET is_sample=1")
        with self.assertRaisesRegex(ValueError, "Full alias index"):
            reconcile_alias_leis(str(self.lei), str(self.alias))


if __name__ == "__main__":
    unittest.main()
