#!/usr/bin/env python3
"""Regression tests for the GLEIF RR historical collision auditor."""
import json
import sqlite3
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))
from audit_gleif_rr_history import audit


def relationship(child, parent, accounting_start, status="ACTIVE"):
    return {
        "RelationshipRecord": {
            "Relationship": {
                "StartNode": {"NodeID": child},
                "EndNode": {"NodeID": parent},
                "RelationshipType": "IS_DIRECTLY_CONSOLIDATED_BY",
                "RelationshipStatus": status,
                "RelationshipPeriods": {"RelationshipPeriod": [
                    {"PeriodType": "ACCOUNTING_PERIOD",
                     "StartDate": accounting_start, "EndDate": "2024-12-31"}
                ]}
            },
            "Registration": {"RegistrationStatus": "PUBLISHED",
                             "LastUpdateDate": accounting_start}
        }
    }


def create_zip(path, records):
    # Match the source parser's line-oriented wrapper format.
    data = '{"RelationshipRecords": [\n'
    data += ',\n'.join(json.dumps(x, indent=2)[1:-1].strip() for x in records)
    data += '\n]}\n'
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("relationships.json", data)


class HistoryAuditTests(unittest.TestCase):
    def test_multiple_periods_and_identical_duplicate(self):
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp) / "rr.zip"
            v1 = relationship("CHILD", "PARENT", "2023-01-01")
            v2 = relationship("CHILD", "PARENT", "2024-01-01", "INACTIVE")
            other = relationship("OTHER", "PARENT", "2024-01-01")
            create_zip(p, [v1, v2, v1, other])
            report = audit([str(p)])
            c = report["counts"]
            self.assertEqual(c["scanned"], 4)
            self.assertEqual(c["supported"], 4)
            self.assertEqual(c["unique_relationship_keys"], 2)
            self.assertEqual(c["duplicate_relationship_keys"], 1)
            self.assertEqual(c["duplicate_source_records_beyond_one_per_key"], 2)
            self.assertEqual(c["keys_with_different_status_or_period_metadata"], 1)
            self.assertEqual(report["examples"][0]["distinct_versions"], 2)

    def test_multiple_snapshots_and_readonly_index(self):
        with tempfile.TemporaryDirectory() as temp:
            folder = Path(temp)
            one, two = folder / "first.zip", folder / "second.zip"
            create_zip(one, [relationship("A", "B", "2023-01-01")])
            create_zip(two, [relationship("A", "B", "2024-01-01")])
            db = folder / "rr.sqlite"
            con = sqlite3.connect(db)
            con.execute("CREATE TABLE relationships (child_lei TEXT, parent_lei TEXT, relationship_type TEXT)")
            con.execute("INSERT INTO relationships VALUES ('A', 'B', 'IS_DIRECTLY_CONSOLIDATED_BY')")
            con.commit()
            con.close()
            report = audit([str(one), str(two)], indexed_db=str(db), sample_limit=0)
            self.assertEqual(report["counts"]["source_files"], 2)
            self.assertEqual(report["counts"]["keys_with_different_status_or_period_metadata"], 1)
            self.assertEqual(report["existing_index"]["rows"], 1)
            self.assertEqual(report["examples"], [])


if __name__ == "__main__":
    unittest.main()
