#!/usr/bin/env python3
"""Regression tests for isolated, lossless Tier-1 evidence staging."""
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))
from build_gleif_tier1_evidence import build


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.source = self.root / "original.zip"
        self.source.write_bytes(b"fixture bytes; the source itself is never modified")
        self.out = self.root / "staged.sqlite"

    def tearDown(self):
        self.temp.cleanup()

    def run_build(self, level, records):
        with patch("build_gleif_tier1_evidence.iter_source", return_value=iter(records)):
            return build(level, str(self.source), str(self.out), progress_every=0)

    def test_names_events_successors_all_preserved(self):
        record = {
            "LEI": {"$": "ABC"},
            "Entity": {
                "LegalName": {"$": "Original Corp"},
                "OtherEntityNames": {"OtherEntityName": [
                    {"$": "Former Alpha", "@type": "PREVIOUS_LEGAL_NAME"},
                    {"$": "Former Beta", "@type": "ALTERNATIVE_LANGUAGE_LEGAL_NAME"},
                ]},
                "TransliteratedOtherEntityNames": {"TransliteratedOtherEntityName":
                    {"$": "Transliterated"}},
                "LegalEntityEvents": {"LegalEntityEvent": [
                    {"LegalEntityEventType": "EVENT_1", "AffectedFields": {
                        "AffectedField": [{"$": "A"}, {"$": "B"}]}},
                    {"LegalEntityEventType": "EVENT_2"},
                ]},
                "SuccessorEntity": [{"SuccessorLEI": "D"}, {"SuccessorLEI": "E"}],
            },
        }
        result = self.run_build("lei", [record])
        self.assertEqual(result["entity_name"], 4)
        self.assertEqual(result["entity_event"], 2)
        self.assertEqual(result["entity_successor"], 2)
        with sqlite3.connect(self.out) as db:
            names = db.execute(
                "SELECT name FROM entity_name ORDER BY source_path, source_ordinal"
            ).fetchall()
            self.assertEqual(len(names), 4)
            self.assertIn(("Former Alpha",), names)
            self.assertIn(("Former Beta",), names)
            events = db.execute("SELECT raw_value_json FROM entity_event ORDER BY source_ordinal").fetchall()
            self.assertEqual(len(json.loads(events[0][0])["AffectedFields"]["AffectedField"]), 2)
            row = db.execute(
                "SELECT source_record_zlib, source_record_sha256 FROM source_observation"
            ).fetchone()
            raw = zlib.decompress(row[0])
            self.assertEqual(hashlib.sha256(raw).hexdigest(), row[1])
            self.assertEqual(json.loads(raw), record)

    def test_repeated_same_type_periods_and_qualifiers_not_collapsed(self):
        rel = {"RelationshipRecord": {
            "Relationship": {
                "StartNode": {"NodeID": "CHILD"},
                "EndNode": {"NodeID": "PARENT"},
                "RelationshipType": "IS_DIRECTLY_CONSOLIDATED_BY",
                "RelationshipPeriods": {"RelationshipPeriod": [
                    {"PeriodType": "ACCOUNTING_PERIOD", "StartDate": "2018"},
                    {"PeriodType": "ACCOUNTING_PERIOD", "StartDate": "2017"},
                ]},
                "RelationshipQualifiers": {"RelationshipQualifier": [
                    {"QualifierCategory": "A"}, {"QualifierCategory": "B"},
                ]},
            }
        }}
        result = self.run_build("rr", [rel])
        self.assertEqual(result["relationship_period"], 2)
        self.assertEqual(result["relationship_qualifier"], 2)
        with sqlite3.connect(self.out) as db:
            dates = db.execute(
                "SELECT start_date FROM relationship_period ORDER BY source_ordinal"
            ).fetchall()
            self.assertEqual(dates, [("2018",), ("2017",)])

    def test_existing_target_is_untouched(self):
        self.out.write_bytes(b"do not replace me")
        with patch("build_gleif_tier1_evidence.iter_source", return_value=iter([])):
            with self.assertRaises(FileExistsError):
                build("lei", str(self.source), str(self.out))
        self.assertEqual(self.out.read_bytes(), b"do not replace me")

    def test_non_sample_snapshot_identification_and_counts(self):
        self.run_build("lei", [{"LEI": {"$": "ABC"}, "Entity": {}}])
        with sqlite3.connect(self.out) as db:
            got = db.execute(
                "SELECT source_archive_sha256, record_count, is_sample FROM source_snapshot"
            ).fetchone()
            self.assertEqual(got, (hashlib.sha256(self.source.read_bytes()).hexdigest(), 1, 0))


if __name__ == "__main__":
    unittest.main()
