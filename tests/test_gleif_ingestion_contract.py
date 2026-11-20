#!/usr/bin/env python3
"""Tests for the fail-closed ingestion contract and source schema drift."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))
from check_gleif_ingestion_contract import evaluate, make_baseline


def audit(level="lei", extra=False, repeats=True):
    rows = [{
        "path": "$.Entity.LegalEntityEvents.LegalEntityEvent",
        "types": {"array": 1},
        "arrays_with_multiple_items": 1 if repeats else 0,
        "max_array_length": 2 if repeats else 1,
    }]
    if extra:
        rows.append({
            "path": "$.Entity.FutureFields.FutureItem",
            "types": {"array": 1},
            "arrays_with_multiple_items": 1,
            "max_array_length": 3,
        })
    return {
        "level": level, "source": "fixture.json.zip",
        "records_scanned": 1, "path_count": len(rows),
        "coverage": "full_requested", "all_paths": rows,
    }


class ContractTests(unittest.TestCase):
    def test_known_unpreserved_array_blocks_even_without_drift(self):
        a = audit()
        report = evaluate(a, make_baseline(a))
        self.assertEqual(report["status"], "BLOCKED")
        self.assertEqual(len(report["unpreserved_or_partially_flattened"]), 1)
        self.assertEqual(report["schema_drift"], [])

    def test_new_field_is_detected_without_auto_approval(self):
        old = audit()
        new = audit(extra=True)
        report = evaluate(new, make_baseline(old))
        self.assertIn("NEW_FIELD_PATH", {x["code"] for x in report["schema_drift"]})
        self.assertIn("$.Entity.FutureFields.FutureItem", report["unreviewed_repeating_paths"])

    def test_existing_field_newly_repeating_is_detected(self):
        old = audit(repeats=False)
        new = audit(repeats=True)
        report = evaluate(new, make_baseline(old))
        codes = {x["code"] for x in report["schema_drift"]}
        self.assertIn("NEW_REPEATING_FIELD", codes)
        self.assertIn("LARGER_ARRAY_OBSERVED", codes)

    def test_partial_audit_cannot_be_approved_as_baseline(self):
        a = audit()
        a["coverage"] = "sampled"
        with self.assertRaisesRegex(ValueError, "Full population"):
            make_baseline(a)

    def test_missing_baseline_is_not_pass(self):
        self.assertEqual(evaluate(audit())["status"], "BLOCKED")


if __name__ == "__main__":
    unittest.main()
