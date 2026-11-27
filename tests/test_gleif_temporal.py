"""Offline GLEIF temporal classification and lossless-period regressions."""
from __future__ import annotations
import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))
from gleif_temporal import assess_relationship
from build_gleif_rr_index import relationship_period_entries, relationship_periods


class TemporalTests(unittest.TestCase):
    def test_duplicate_accounting_periods_preserved_in_order(self):
        rel = {"RelationshipPeriods": {"RelationshipPeriod": [
            {"PeriodType": "ACCOUNTING_PERIOD",
             "StartDate": "2018-01-01", "EndDate": "2018-12-31"},
            {"PeriodType": "ACCOUNTING_PERIOD",
             "StartDate": "2019-01-01", "EndDate": "2019-12-31"},
            {"PeriodType": "RELATIONSHIP_PERIOD",
             "StartDate": "2018-01-01"},
        ]}}
        entries = relationship_period_entries(rel)
        self.assertEqual(len(entries), 3)
        self.assertEqual([e["ordinal"] for e in entries], [0, 1, 2])
        self.assertEqual([e["end"] for e in entries[:2]],
                         ["2018-12-31", "2019-12-31"])
        # The flat projection exists for backward compatibility only.
        self.assertEqual(relationship_periods(rel)["ACCOUNTING_PERIOD"][1],
                         "2018-12-31")

    def test_lapsed_old_accounting_is_unresolved_not_divestiture(self):
        row = {"relationship_status": "ACTIVE",
               "registration_status": "LAPSED",
               "relationship_start": "2018-01-01",
               "accounting_start": "2018-01-01",
               "accounting_end": "2018-12-31"}
        out = assess_relationship(row, date(2026, 11, 26))
        self.assertEqual(out["classification"], "CURRENT_UNRESOLVED")
        self.assertFalse(out["asm_scope_authorized"])
        self.assertFalse(out["accounting_end_is_divestiture"])

    def test_recent_published_active_is_supported_but_not_ownership_proof(self):
        row = {"relationship_status": "ACTIVE",
               "registration_status": "PUBLISHED"}
        periods = [
            {"period_type": "RELATIONSHIP_PERIOD", "start_date": "2019-01-01", "end_date": None},
            {"period_type": "ACCOUNTING_PERIOD", "start_date": "2025-01-01", "end_date": "2025-12-31"},
        ]
        out = assess_relationship(row, date(2026, 11, 26), periods)
        self.assertEqual(out["classification"], "CURRENT_SUPPORTED")
        self.assertFalse(out["snapshot_ownership_proven"])

    def test_explicitly_ended_inactive_is_historical_only(self):
        row = {"relationship_status": "INACTIVE", "registration_status": "PUBLISHED",
               "relationship_start": "2018-01-01", "relationship_end": "2020-12-31"}
        out = assess_relationship(row, date(2026, 11, 26))
        self.assertEqual(out["classification"], "HISTORICAL_ONLY")
        self.assertFalse(out["historical_control_proven"])

    def test_active_with_ended_period_remains_unresolved(self):
        row = {"relationship_status": "ACTIVE", "registration_status": "PUBLISHED",
               "relationship_start": "2018-01-01", "relationship_end": "2020-12-31"}
        out = assess_relationship(row, date(2026, 11, 26))
        self.assertEqual(out["classification"], "CURRENT_UNRESOLVED")
        self.assertIn("EXPLICIT_RELATIONSHIP_PERIOD_ENDED", out["reasons"])

    def test_missing_dates_not_current_supported(self):
        out = assess_relationship({"relationship_status": "ACTIVE",
                                   "registration_status": "PUBLISHED"},
                                  date(2026, 11, 26))
        self.assertEqual(out["classification"], "CURRENT_UNRESOLVED")


if __name__ == "__main__":
    unittest.main()
