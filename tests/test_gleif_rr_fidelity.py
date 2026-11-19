#!/usr/bin/env python3
"""Unit tests for source-to-RR-index fidelity auditing."""
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))
from audit_gleif_rr_fidelity import inspect, ALL_COLUMNS, map_record


def wrapper(accounting_end="2024-12-31", status="ACTIVE", repeat=False):
    periods = [{
        "PeriodType": "ACCOUNTING_PERIOD",
        "StartDate": "2024-01-01", "EndDate": accounting_end,
    }]
    if repeat:
        periods.append({
            "PeriodType": "ACCOUNTING_PERIOD",
            "StartDate": "2023-01-01", "EndDate": "2023-12-31",
        })
    return {"RelationshipRecord": {
        "Relationship": {
            "StartNode": {"NodeID": "C"},
            "EndNode": {"NodeID": "P"},
            "RelationshipType": "IS_DIRECTLY_CONSOLIDATED_BY",
            "RelationshipStatus": status,
            "RelationshipPeriods": {"RelationshipPeriod": periods},
        },
        "Registration": {"RegistrationStatus": "PUBLISHED"},
    }}


class FidelityTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.db = Path(self.folder.name) / "rr.sqlite"
        con = sqlite3.connect(self.db)
        con.execute("CREATE TABLE relationships (" + ", ".join(f"{c} TEXT" for c in ALL_COLUMNS) + ")")
        con.execute("CREATE TABLE index_metadata (key TEXT, value TEXT)")
        con.execute("INSERT INTO index_metadata VALUES ('source_file','example.zip')")
        con.commit()
        con.close()

    def tearDown(self):
        self.folder.cleanup()

    def insert(self, raw):
        disposition, _, values, _ = map_record(raw)
        self.assertEqual(disposition, "supported")
        con = sqlite3.connect(self.db)
        con.execute("INSERT INTO relationships VALUES (" + ",".join("?" for _ in ALL_COLUMNS) + ")", values)
        con.commit()
        con.close()

    def check(self, raw):
        with patch("audit_gleif_rr_fidelity.records", return_value=iter([raw])):
            return inspect("example.zip", str(self.db))

    def test_equal_source_index_fields(self):
        raw = wrapper()
        self.insert(raw)
        result = self.check(raw)
        self.assertEqual(result["counts"]["rows_matching_all_compared_fields"], 1)
        self.assertEqual(result["counts"]["index_keys_absent_from_source"], 0)
        self.assertEqual(result["fields_with_mismatches"], {})
        self.assertTrue(result["source_filename_matches_index_metadata"])

    def test_detects_wrong_date_and_missing_row(self):
        raw = wrapper()
        self.insert(wrapper(accounting_end="2019-12-31"))
        result = self.check(raw)
        self.assertEqual(result["counts"]["rows_with_field_mismatch"], 1)
        self.assertEqual(result["fields_with_mismatches"]["accounting_end"], 1)
        with patch("audit_gleif_rr_fidelity.records", return_value=iter([
            {**raw, "RelationshipRecord": {
                **raw["RelationshipRecord"],
                "Relationship": {
                    **raw["RelationshipRecord"]["Relationship"],
                    "StartNode": {"NodeID": "NOT_IN_INDEX"},
                }
            }}
        ])):
            result = inspect("example.zip", str(self.db))
        self.assertEqual(result["counts"]["missing_in_index"], 1)
        self.assertEqual(result["counts"]["index_keys_absent_from_source"], 1)

    def test_repeated_period_flags_possible_flattening_loss(self):
        raw = wrapper(repeat=True)
        self.insert(raw)
        result = self.check(raw)
        self.assertEqual(result["records_with_repeated_period_type"]["ACCOUNTING_PERIOD"], 1)


if __name__ == "__main__":
    unittest.main()
