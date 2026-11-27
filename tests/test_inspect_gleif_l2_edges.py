"""Offline tests for exact-LEI pair inspection; no production mutation."""
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))
from eval.inspect_gleif_l2_edges import inspect


def report(counterparty_lei="PARENT"):
    return {
        "comparison_as_of_date":"2026-11-26",
        "companies":[{
            "id":"monsanto","company":"Monsanto Company",
            "gleif_seed_current":{"exact_seed_leis":["CHILD"],"status":"REVIEW_REQUIRED"},
            "sentinel_events":[{
                "counterparty":"Bayer Aktiengesellschaft",
                "event_date":"2018-06-07",
                "gleif_counterparty_current":{"exact_seed_leis":[counterparty_lei]},
                "sec":{"event_extracted":False},
            }],
        }],
    }


class L2EdgeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.path=Path(self.tmp.name)/"gleif.sqlite"
        conn=sqlite3.connect(self.path)
        conn.execute("""CREATE TABLE relationships (
            child_lei TEXT, parent_lei TEXT, relationship_type TEXT,
            relationship_status TEXT, relationship_start TEXT, relationship_end TEXT)""")
        conn.execute("""INSERT INTO relationships VALUES
            ('CHILD','PARENT','IS_DIRECTLY_CONSOLIDATED_BY','ACTIVE',
             '2019-01-01',NULL)""")
        conn.commit();conn.close()

    def tearDown(self):
        self.tmp.cleanup()

    def test_exact_lei_review_status_does_not_hide_raw_edge(self):
        pair=inspect(report(),str(self.path))["pairs"][0]
        self.assertEqual(pair["edge_check"],"EDGE_RECORDS_FOUND")
        self.assertEqual(len(pair["relationship_records"]),1)
        edge=pair["relationship_records"][0]
        self.assertTrue(edge["current"]["current_snapshot_eligible_at_as_of"])
        self.assertFalse(edge["event_date"]["current_snapshot_eligible_at_as_of"])
        self.assertFalse(edge["event_date"]["historical_status_proven"])
        self.assertEqual(pair["policy_decision"],"EVIDENCE_ONLY_NOT_ACQUISITION")

    def test_unmatched_leis_no_pair_edge(self):
        pair=inspect(report("OTHER"),str(self.path))["pairs"][0]
        self.assertEqual(pair["edge_check"],"NO_DIRECT_PAIR_RECORD")

    def test_missing_exact_anchor_is_not_a_negative_edge(self):
        pair=inspect(report(""),str(self.path))["pairs"][0]
        self.assertEqual(pair["edge_check"],"NOT_CHECKED_NO_UNIQUE_EXACT_LEIS")

    def test_missing_database_raises(self):
        with self.assertRaises(FileNotFoundError):
            inspect(report(),str(Path(self.tmp.name)/"missing.sqlite"))


if __name__=="__main__":
    unittest.main()
