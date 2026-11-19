#!/usr/bin/env python3
"""Focused regression tests for GLEIF cardinality discovery."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))
from audit_gleif_cardinality import CardinalityInventory


def rr(periods):
    return {"RelationshipRecord": {
        "Relationship": {
            "RelationshipType": {"$": "IS_DIRECTLY_CONSOLIDATED_BY"},
            "RelationshipPeriods": {"RelationshipPeriod": periods},
        },
        "Registration": {"RegistrationStatus": {"$": "PUBLISHED"}},
    }}


class CardinalityTests(unittest.TestCase):
    def test_two_periods_do_not_collapse(self):
        inv = CardinalityInventory(example_limit=3)
        periods = [
            {"PeriodType": "ACCOUNTING_PERIOD", "StartDate": "2018-01-01"},
            {"PeriodType": "ACCOUNTING_PERIOD", "StartDate": "2019-01-01"},
        ]
        inv.observe(rr(periods), "rr")
        result = inv.report("rr", "rr.json.zip", None)
        self.assertEqual(result["repeated_rr_period_types"], {"ACCOUNTING_PERIOD": 1})
        paths = {x["path"]: x for x in result["all_paths"]}
        key = "$.RelationshipRecord.Relationship.RelationshipPeriods.RelationshipPeriod"
        self.assertEqual(paths[key]["max_array_length"], 2)
        self.assertEqual(paths[key]["arrays_with_multiple_items"], 1)
        self.assertEqual(paths[key]["examples"][0]["array_length"], 2)

    def test_single_period_object_and_array_are_distinct_shapes(self):
        inv = CardinalityInventory()
        inv.observe(rr({"PeriodType": "ACCOUNTING_PERIOD"}), "rr")
        inv.observe(rr([{"PeriodType": "ACCOUNTING_PERIOD"}]), "rr")
        result = inv.report("rr", "rr.json.zip", 2)
        matches = [x for x in result["paths_with_multiple_shapes"]
                   if x["path"].endswith(".RelationshipPeriod")]
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["types"], {"object": 1, "array": 1})

    def test_level_one_previous_names_array(self):
        inv = CardinalityInventory()
        inv.observe({"Entity": {"OtherEntityNames": {"OtherEntityName": [
            {"$": "Former Co"}, {"$": "Former Holdings"}
        ]}}}, "lei")
        report = inv.report("lei", "lei.json", 1)
        repeated_paths = [x["path"] for x in report["paths_with_multi_value_arrays"]]
        self.assertTrue(any("OtherEntityName" in x for x in repeated_paths))
        self.assertEqual(report["repeated_rr_period_types"], {})

    def test_limit_on_distinct_paths(self):
        inv = CardinalityInventory(max_paths=2)
        with self.assertRaises(RuntimeError):
            inv.observe({"A": 1, "B": 2}, "lei")


if __name__ == "__main__":
    unittest.main()
