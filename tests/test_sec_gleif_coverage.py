"""Offline regression tests: read-only SEC/GLEIF discovery coverage."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))

from eval.compare_sec_gleif_coverage import compare, attempt_resolution


def root(name, lei="12345678901234567890"):
    return SimpleNamespace(
        status="AUTO_RESOLVED", confidence="MEDIUM", reason="fixture",
        root=SimpleNamespace(lei=lei, legal_name=name, entity_status="ACTIVE"),
        candidates=[], seed_matches=[{
            "lei":lei, "legal_name":name,"entity_status":"ACTIVE",
        }],
    )


class CoverageTests(unittest.TestCase):
    def test_independent_sources_and_exact_cik_lei_distinction(self):
        study={"study_id":"S","companies":[{"id":"monsanto","company":"Monsanto Company",
                                          "cik":"0001110783"}]}
        gold={"events":[{"id":"m","counterparty":"Bayer Aktiengesellschaft",
                         "approx_date":"2018-06-07","event_type":"ACQUIRED",
                         "status":"COMPLETED"}]}
        sec={"gold_events":[{"id":"m","stages":{
            "event_extracted":False,"candidate_emitted":True,
        }}],"retrieval":{"errors":[]}}
        calls=[]
        def fake_resolve(name,lei_db,rr_db,*,as_of_date):
            calls.append((name,as_of_date))
            return root(name)
        with tempfile.TemporaryDirectory() as td:
            directory=Path(td)
            (directory/"res").mkdir()
            (directory/"gold").mkdir()
            (directory/"res"/"monsanto.json").write_text(json.dumps(sec))
            (directory/"gold"/"monsanto.json").write_text(json.dumps(gold))
            result=compare(study,directory/"res",directory/"gold",
                           "l1.sqlite","l2.sqlite",as_of="2026-11-26",
                           resolver=fake_resolve)
        company=result["companies"][0]
        self.assertEqual(company["identifiers"]["sec_cik"],"0001110783")
        self.assertIsNone(company["identifiers"]["gleif_lei"])
        row=company["sentinel_events"][0]
        self.assertFalse(row["sec"]["matching_event_and_candidate"])
        self.assertTrue(row["sec"]["counterparty_candidate_emitted"])
        self.assertFalse(row["acquisition_inferred_from_gleif"])
        self.assertEqual(row["gleif_counterparty_current"]["status"],"AUTO_RESOLVED")
        self.assertEqual(row["gleif_counterparty_at_event_date"]["as_of_date"],"2018-06-07")
        self.assertEqual(len(calls),4)  # two entities, two as-of dates
        self.assertFalse(result["policy"]["provider_results_reconciled_into_graph"])

    def test_no_sec_file_is_not_false_negative(self):
        study={"study_id":"S","companies":[{"id":"x","company":"X","cik":"123"}]}
        with tempfile.TemporaryDirectory() as td:
            d=Path(td);(d/"gold").mkdir()
            (d/"gold"/"x.json").write_text(json.dumps(
                {"events":[{"id":"x1","counterparty":"Y"}]}))
            report=compare(study,d/"missing",d/"gold","a","b",
                           as_of="2026-11-26",resolver=lambda n,a,b,**kw:root(n))
        row=report["companies"][0]["sentinel_events"][0]
        self.assertEqual(row["sec"]["check"],"NOT_CHECKED")
        self.assertIsNone(row["sec"]["event_extracted"])

    def test_missing_database_is_error_not_no_match(self):
        def fail(*a,**kw):
            raise FileNotFoundError("gleif_lei.sqlite")
        result=attempt_resolution("GE", "2026-11-26",fail,"a","b")
        self.assertEqual(result["status"],"ERROR")
        self.assertNotEqual(result["status"],"NO_MATCH")

    def test_ambiguous_resolution_not_endorsed(self):
        def ambiguous(*a,**kw):
            return SimpleNamespace(status="REVIEW_REQUIRED",confidence="LOW",
                reason="multiple",root=None,candidates=[],seed_matches=[])
        result=attempt_resolution("Alstom","2026-11-26",ambiguous,"a","b")
        self.assertEqual(result["status"],"REVIEW_REQUIRED")
        self.assertIsNone(result["endorsed_root"])


if __name__=="__main__":
    unittest.main()
