"""Offline importer smoke test: source ZIP -> SQLite -> typed periods."""
from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "code" / "build_gleif_rr_index.py"


class GLEIFRRImporterIntegration(unittest.TestCase):
    def test_build_preserves_all_periods_and_raw_record(self):
        record = {
            "RelationshipRecord": {
                "Relationship": {
                    "StartNode": {"NodeID": "LEI-CHILD"},
                    "EndNode": {"NodeID": "LEI-PARENT"},
                    "RelationshipType": "IS_DIRECTLY_CONSOLIDATED_BY",
                    "RelationshipStatus": "ACTIVE",
                    "RelationshipPeriods": {
                        "RelationshipPeriod": [
                            {"PeriodType": "RELATIONSHIP_PERIOD",
                             "StartDate": "2018-01-01"},
                            {"PeriodType": "ACCOUNTING_PERIOD",
                             "StartDate": "2018-01-01",
                             "EndDate": "2018-12-31"},
                            {"PeriodType": "ACCOUNTING_PERIOD",
                             "StartDate": "2025-01-01",
                             "EndDate": "2025-12-31"},
                        ]
                    }
                },
                "Registration": {
                    "RegistrationStatus": "PUBLISHED",
                    "LastUpdateDate": "2026-07-31"
                }
            }
        }
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            source = base / "source.zip"
            target = base / "gleif_rr_test.sqlite"
            with zipfile.ZipFile(source, "w", zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("source.json", json.dumps(record, indent=2))
            proc = subprocess.run(
                [sys.executable, str(SCRIPT), "--zip", str(source),
                 "--out", str(target), "--batch-size", "1",
                 "--progress-every", "0"],
                capture_output=True, text=True, check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            with sqlite3.connect(target) as con:
                con.row_factory = sqlite3.Row
                rows = con.execute("SELECT * FROM relationships").fetchall()
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0]["accounting_end"], "2018-12-31")
                self.assertEqual(
                    json.loads(rows[0]["raw_record_json"]), record["RelationshipRecord"]
                )
                periods = con.execute(
                    "SELECT * FROM relationship_periods ORDER BY period_ordinal"
                ).fetchall()
                self.assertEqual(len(periods), 3)
                self.assertEqual(
                    [x["period_type"] for x in periods],
                    ["RELATIONSHIP_PERIOD", "ACCOUNTING_PERIOD", "ACCOUNTING_PERIOD"]
                )
                self.assertEqual(periods[-1]["end_date"], "2025-12-31")
                self.assertEqual(
                    json.loads(periods[-1]["raw_period_json"])["PeriodType"],
                    "ACCOUNTING_PERIOD",
                )
                self.assertEqual(
                    con.execute(
                        "SELECT value FROM index_metadata WHERE key='build_status'"
                    ).fetchone()[0],
                    "complete"
                )


if __name__ == "__main__":
    unittest.main()
