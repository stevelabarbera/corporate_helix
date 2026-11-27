"""Offline safety checks for auditable LEI/CIK identity bridging."""
from __future__ import annotations

import csv
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))

from sec_identity_bridge import lookup_crosswalk, normalize_cik, resolve_sec_identity


class IdentityBridgeTests(unittest.TestCase):
    def write_csv(self, rows):
        temp = tempfile.TemporaryDirectory()
        path = Path(temp.name) / "bridge.csv"
        with path.open("w", newline="", encoding="utf-8") as fp:
            out = csv.DictWriter(fp, fieldnames=[
                "lei", "cik", "verification_status", "evidence_url",
            ])
            out.writeheader()
            out.writerows(rows)
        self.addCleanup(temp.cleanup)
        return str(path)

    def test_verified_leicik_with_evidence(self):
        path = self.write_csv([{
            "lei": "ABC", "cik": "1110783",
            "verification_status": "VERIFIED",
            "evidence_url": "https://www.sec.gov/example",
        }])
        result = lookup_crosswalk("abc", path)
        self.assertEqual(result["cik"], "0001110783")
        self.assertEqual(result["status"], "VERIFIED_CROSSWALK")

    def test_conflicting_cik_never_resolves(self):
        path = self.write_csv([
            {"lei": "ABC", "cik": "1110783", "verification_status": "VERIFIED",
             "evidence_url": "https://www.sec.gov/example"},
            {"lei": "ABC", "cik": "1000001", "verification_status": "CANDIDATE",
             "evidence_url": ""},
        ])
        result = resolve_sec_identity("Company", "ABC", "Agent",
                                      crosswalk_path=path,
                                      ticker_lookup=lambda n,a: "1110783")
        self.assertEqual(result["status"], "AMBIGUOUS_CROSSWALK")
        self.assertIsNone(result["cik"])

    def test_missing_evidence_stays_unverified(self):
        path = self.write_csv([{
            "lei": "ABC", "cik": "1110783",
            "verification_status": "VERIFIED", "evidence_url": "",
        }])
        self.assertEqual(lookup_crosswalk("ABC", path)["status"],
                         "UNVERIFIED_CROSSWALK")

    def test_ticker_lookup_candidate_not_verified(self):
        result = resolve_sec_identity("A Corp", "ABC", "Agent",
                                      ticker_lookup=lambda n,a: "2095096")
        self.assertEqual(result["cik"], "0002095096")
        self.assertFalse(result["identity_verified_lei_cik"])
        self.assertEqual(result["status"], "TICKER_EXACT_NAME_CANDIDATE")

    def test_no_match_is_not_fabricated(self):
        result = resolve_sec_identity("Missing", "ABC", "Agent",
                                      ticker_lookup=lambda n,a: None)
        self.assertEqual(result["status"], "NO_SEC_IDENTITY")
        self.assertIsNone(result["cik"])

    def test_malformed_cik_rejected(self):
        for value in ["LEI-ABC", "0", "12345678901", "1a2"]:
            self.assertIsNone(normalize_cik(value))


if __name__ == "__main__":
    unittest.main()
