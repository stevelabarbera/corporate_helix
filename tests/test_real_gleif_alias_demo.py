#!/usr/bin/env python3
"""Demonstration guardrails: real evidence, no fake ownership claims."""
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))
from demo_real_gleif_alias import run_demo


class RealAliasDemoTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        base = Path(self.folder.name)
        self.lei = base / "lei.sqlite"
        self.rr = base / "rr.sqlite"
        self.evidence = base / "sample.sqlite"
        with sqlite3.connect(self.lei) as db:
            db.executescript("""
                CREATE TABLE lei_entities (
                    lei TEXT PRIMARY KEY, legal_name TEXT,
                    legal_name_normalized TEXT, legal_jurisdiction TEXT, entity_status TEXT
                );
                INSERT INTO lei_entities VALUES
                  ('ABC', 'CURRENT LEGAL ENTITY LTD', 'current legal entity ltd', 'GB', 'ACTIVE');
            """)
        with sqlite3.connect(self.rr) as db:
            db.executescript("""
                CREATE TABLE relationships (
                    child_lei TEXT, parent_lei TEXT,
                    relationship_type TEXT, relationship_status TEXT
                );
            """)
        with sqlite3.connect(self.evidence) as db:
            db.executescript("""
                CREATE TABLE source_snapshot (
                    source_level TEXT, is_sample INTEGER,
                    source_archive_sha256 TEXT, record_count INTEGER
                );
                INSERT INTO source_snapshot VALUES ('lei',1,'fixture-hash',1);
                CREATE TABLE source_observation (
                    observation_id INTEGER PRIMARY KEY,
                    record_identifier TEXT, source_ordinal INTEGER
                );
                INSERT INTO source_observation VALUES (1,'ABC',14);
                CREATE TABLE entity_name (
                    observation_id INTEGER, source_path TEXT,
                    source_ordinal INTEGER, name TEXT,
                    name_normalized TEXT, raw_value_json TEXT
                );
                INSERT INTO entity_name VALUES
                  (1,'Entity.LegalName',0,'CURRENT LEGAL ENTITY LTD',
                   'current legal entity ltd','{}'),
                  (1,'Entity.OtherEntityNames.OtherEntityName',0,
                   'OLD LEGAL ENTITY LTD','old legal entity ltd',
                   '{"$":"OLD LEGAL ENTITY LTD","@type":"PREVIOUS_LEGAL_NAME"}');
            """)

    def tearDown(self):
        self.folder.cleanup()

    def test_real_record_only_alias_requires_review(self):
        result = run_demo(str(self.evidence), str(self.lei), str(self.rr))
        self.assertEqual(result["status"], "DEMONSTRATED")
        self.assertEqual(result["source_lei"], "ABC")
        self.assertEqual(result["query"], "OLD LEGAL ENTITY LTD")
        self.assertEqual(result["resolution_status"], "REVIEW_REQUIRED")
        self.assertEqual(result["resolution_confidence"], "LOW")
        self.assertIs(result["ownership_verified"], False)
        self.assertTrue(result["evidence_is_sample"])

    def test_unavailable_alias_is_not_fabricated(self):
        result = run_demo(str(self.evidence), str(self.lei), str(self.rr),
                          preferred_alias="name not in evidence")
        self.assertEqual(result["status"], "NO_DEMONSTRABLE_ALIAS")

    def test_canonical_match_does_not_count_as_new_alias_discovery(self):
        with sqlite3.connect(self.lei) as db:
            db.execute("""INSERT INTO lei_entities VALUES (
              'OTHER','OLD LEGAL ENTITY LTD','old legal entity ltd','US','ACTIVE'
            )""")
        result = run_demo(str(self.evidence), str(self.lei), str(self.rr))
        self.assertEqual(result["status"], "NO_DEMONSTRABLE_ALIAS")


if __name__ == "__main__":
    unittest.main()
