#!/usr/bin/env python3
"""Paired alias discovery benchmark controls: same cohorts, review-only, no accuracy claim."""
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))
from benchmark_alias_identity_discovery import load_cohort, run
from build_compact_gleif_alias_index import SCHEMA as COMPACT_ALIAS_SCHEMA


class PairedBenchmarkTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        self.lei, self.rr, self.alias = (d / x for x in ("lei.sqlite", "rr.sqlite", "alias.sqlite"))
        with sqlite3.connect(self.lei) as db:
            db.executescript("""
            CREATE TABLE lei_entities (
                lei TEXT PRIMARY KEY, legal_name TEXT, legal_name_normalized TEXT,
                legal_jurisdiction TEXT, entity_status TEXT);
            INSERT INTO lei_entities VALUES
                ('X','Modern Entity Ltd','modern entity ltd','GB','ACTIVE'),
                ('Y','Another Entity Ltd','another entity ltd','US','ACTIVE');
            """)
        with sqlite3.connect(self.rr) as db:
            db.executescript("""
            CREATE TABLE relationships (
                child_lei TEXT, parent_lei TEXT, relationship_type TEXT,
                relationship_status TEXT);
            """)
        with sqlite3.connect(self.alias) as db:
            # Reuse the production compact-index DDL so fixture and resolver
            # cannot silently drift apart on source_snapshot or child columns.
            db.executescript(COMPACT_ALIAS_SCHEMA)
            db.executescript("""
            INSERT INTO source_snapshot VALUES ('lei','fixture.zip','fixture',2,2,0);
            INSERT INTO source_observation
                (observation_id,source_ordinal,record_identifier)
                VALUES (1,1,'X'),(2,2,'Y');
            INSERT INTO entity_name VALUES
                (1,'Entity.OtherEntityNames.OtherEntityName',0,
                 'Old Entity Ltd','old entity ltd','{"$":"Old Entity Ltd"}'),
                (2,'Entity.OtherEntityNames.OtherEntityName',0,
                 'Shared Legacy','shared legacy','{"$":"Shared Legacy"}');
            """)

    def tearDown(self):
        self.tmp.cleanup()

    def test_discovery_delta_not_mislabeled_accuracy(self):
        result = run(["Old Entity Ltd", "Modern Entity Ltd", "Missing Corp"],
                     str(self.lei), str(self.rr), str(self.alias))
        cases = {v["company"]: v for v in result["cases"]}
        old = cases["Old Entity Ltd"]
        self.assertEqual(old["canonical_only"]["status"], "NO_MATCH")
        self.assertEqual(old["alias_enabled"]["status"], "REVIEW_REQUIRED")
        self.assertEqual(old["alias_enabled"]["confidence"], "LOW")
        self.assertEqual(old["new_candidate_leis"], ["X"])
        self.assertEqual(old["identity_correctness"], "NOT_SCORED")
        self.assertFalse(old["ownership_verified"])
        current = cases["Modern Entity Ltd"]
        self.assertEqual(current["canonical_only"], current["alias_enabled"])
        self.assertFalse(current["new_seed_discovered"])
        self.assertEqual(cases["Missing Corp"]["alias_enabled"]["status"], "NO_MATCH")
        self.assertEqual(result["summary"]["companies_with_new_leis"], 1)
        self.assertEqual(result["summary"]["previously_no_match_now_has_seeds"], 1)

    def test_duplicate_cohort_rejected(self):
        file = Path(self.tmp.name) / "cohort.txt"
        file.write_text("Old Entity Ltd\nOld Entity Ltd\n")
        with self.assertRaises(ValueError):
            load_cohort(file)

    def test_json_cohort(self):
        file = Path(self.tmp.name) / "cohort.json"
        file.write_text(json.dumps({"companies": ["One", {"company": "Two"}]}))
        names, _ = load_cohort(file)
        self.assertEqual(names, ["One", "Two"])

    def test_reject_sample_index(self):
        with sqlite3.connect(self.alias) as db:
            db.execute("UPDATE source_snapshot SET is_sample=1")
        with self.assertRaisesRegex(ValueError, "full alias index"):
            run(["Old Entity Ltd"], str(self.lei), str(self.rr), str(self.alias))


if __name__ == "__main__":
    unittest.main()
