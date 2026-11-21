#!/usr/bin/env python3
"""Verification tests exercising two separately implemented JSON reader paths."""
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))
from build_gleif_tier1_evidence import build
from verify_gleif_tier1_evidence import verify


def rr(child, periods):
    return {"RelationshipRecord": {"Relationship": {
        "StartNode": {"NodeID": child},
        "EndNode": {"NodeID": "PARENT"},
        "RelationshipType": "IS_DIRECTLY_CONSOLIDATED_BY",
        "RelationshipPeriods": {"RelationshipPeriod": periods},
        "RelationshipQualifiers": {"RelationshipQualifier": [
            {"QualifierCategory": "QUALIFIER_A"}, {"QualifierCategory": "QUALIFIER_B"}
        ]},
    }}}


class ReplayTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.source = root / "rr.json.zip"
        self.db = root / "rr_stage.sqlite"

    def tearDown(self):
        self.temp.cleanup()

    def make_source(self):
        records = [
            rr("C1", [{"PeriodType": "ACCOUNTING_PERIOD", "StartDate": "2018"},
                      {"PeriodType": "ACCOUNTING_PERIOD", "StartDate": "2017"}]),
            rr("C2", [{"PeriodType": "RELATIONSHIP_PERIOD", "StartDate": "2024"}]),
            rr("C3", [{"PeriodType": "ACCOUNTING_PERIOD", "StartDate": "2016"}]),
        ]
        with zipfile.ZipFile(self.source, "w", zipfile.ZIP_DEFLATED) as output:
            output.writestr("relationship.json", json.dumps({"records": records}))
        return records

    def test_independent_rr_parser_finds_original_duplicate_periods(self):
        records = self.make_source()
        with patch("build_gleif_tier1_evidence.iter_source", return_value=iter(records)):
            counts = build("rr", str(self.source), str(self.db),
                           record_ordinals=[1, 3], progress_every=0)
        self.assertEqual(counts["source_observation"], 2)
        self.assertEqual(counts["relationship_period"], 3)
        result = verify(self.source, self.db)
        self.assertEqual(result["status"], "PASS", result)
        self.assertEqual(result["source_records_verified"], 2)
        self.assertEqual(result["tier1_elements_verified"]["relationship_qualifier"], 4)

    def test_fails_on_corrupted_child_even_when_full_raw_record_matches(self):
        records = self.make_source()
        with patch("build_gleif_tier1_evidence.iter_source", return_value=iter(records)):
            build("rr", str(self.source), str(self.db), max_records=2, progress_every=0)
        with sqlite3.connect(self.db) as conn:
            conn.execute("UPDATE relationship_period SET start_date='CORRUPT' WHERE source_ordinal=0")
            conn.commit()
        # Raw source child payload is still intact: child scalar columns also
        # need verification, so this mismatch must be caught.
        result = verify(self.source, self.db)
        self.assertEqual(result["status"], "FAIL")

    def test_refuses_missing_requested_ordinal(self):
        records = self.make_source()
        with patch("build_gleif_tier1_evidence.iter_source", return_value=iter(records)):
            with self.assertRaisesRegex(RuntimeError, "not found"):
                build("rr", str(self.source), str(self.db),
                      record_ordinals=[99], progress_every=0)
        self.assertFalse(self.db.exists())


if __name__ == "__main__":
    unittest.main()
