#!/usr/bin/env python3
"""Challenge cohort: never confuse missing evidence with negative M&A truth."""
from pathlib import Path
import json
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "code" / "eval"))
import run_ma_challenge16 as challenge


class Challenge16Tests(unittest.TestCase):
    def test_frozen_16_original_names(self):
        study = challenge.cohort(ROOT / "data/eval_study/ma_challenge16_v1.json")
        names = [c["query"] for c in study["companies"]]
        self.assertEqual(len(names), 16)
        self.assertEqual(names[0], "Constellation Software")
        self.assertEqual(names[11], "Exon Mobile")
        self.assertEqual(names[13], "The Proctor and gamble Company")
        self.assertEqual(names[-1], "Monsanto")

    def test_sec_name_miss_is_not_no_ma_claim(self):
        result = challenge.sec_probe(
            "Grub Market", "Test Researcher researcher@validdomain.test",
            tickers={"0": {"title": "Other Company Inc", "cik_str": 12345}},
        )
        self.assertEqual(result["state"], "NO_EXACT_TICKER_NAME_MATCH")
        self.assertIsNone(result["cik"])
        self.assertIn("not proof", result["note"])

    def test_sec_matched_name(self):
        result = challenge.sec_probe(
            "Exact Corp", "Test Researcher researcher@validdomain.test",
            tickers={"0": {"title": "Exact Corp", "cik_str": 12345}},
        )
        self.assertEqual(result["state"], "MATCHED")
        self.assertEqual(result["cik"], "0000012345")

    def test_live_expansion_without_cik_is_not_sec_retrieval(self):
        class NoopProvider:
            def __init__(self, *args, **kwargs):
                pass
            def __call__(self, pivot, iteration):
                return []
        with patch.object(challenge, "GleifIdentityFallbackProvider", NoopProvider):
            outcome = challenge.expansion_probe(
                "Private Enterprise", None, "Test Person test@validdomain.test",
                "unused_lei.sqlite", "unused_rr.sqlite", "2015-01-01", "2026-11-24", 1,
                provider_factory=NoopProvider,
            )
        self.assertEqual(outcome["state"], "COMPLETED", outcome)
        self.assertEqual(outcome["sec_retrieval"], "NOT_ATTEMPTED_NO_CIK")
        self.assertIsNone(outcome["filings_with_selected_sections"])
        self.assertEqual(outcome["ma_evidence_events"], [])

    def test_identity_errors_are_observable(self):
        with patch.object(challenge, "resolve_company_root", side_effect=RuntimeError("fixture")):
            result = challenge.identity_probe("Acme", "x", "y", "z")
        self.assertEqual(result["state"], "ERROR")
        self.assertIn("fixture", result["error"])

    def test_summary_separates_errors_and_discovery(self):
        rows = [{
            "gleif_identity": {"state": "COMPLETED", "status": "REVIEW_REQUIRED"},
            "sec_directory": {"state": "NO_EXACT_TICKER_NAME_MATCH"},
            "ma_pipeline": {"state": "COMPLETED",
                            "ma_evidence_events": [], "review_candidate_entities": []},
        }, {
            "gleif_identity": {"state": "ERROR"},
            "sec_directory": {"state": "ERROR"},
            "ma_pipeline": {"state": "NOT_ATTEMPTED_SEC_DIRECTORY_ERROR"},
        }]
        counts = challenge.summarize(rows)
        self.assertEqual(counts["gleif_needs_review"], 1)
        self.assertEqual(counts["gleif_query_errors"], 1)
        self.assertEqual(counts["sec_ticker_name_misses"], 1)
        self.assertEqual(counts["sec_ticker_errors"], 1)
        self.assertEqual(counts["pipeline_evidence_events"], 0)


if __name__ == "__main__":
    unittest.main()
