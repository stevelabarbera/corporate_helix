from pathlib import Path
import json
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code" / "eval"))
from summarize_ma_recall_four import summarize

class RecallFourSummaryTests(unittest.TestCase):
    def test_unrun_is_not_zero_recall(self):
        study={"study_id":"fixture","companies":[{"id":"x","company":"X","cik":"1"}]}
        with tempfile.TemporaryDirectory() as directory:
            result=summarize(study, directory)
        self.assertEqual(result["companies_ran"], 0)
        self.assertIsNone(result["sentinel_event_detection_fraction"])
        self.assertEqual(result["companies"][0]["run_state"], "NOT_RUN")

    def test_stage_failure_uses_existing_baseline_measurement(self):
        study={"study_id":"fixture","companies":[{"id":"x","company":"X","cik":"1"}]}
        with tempfile.TemporaryDirectory() as directory:
            data={
                "cik":"1", "retrieval":{"filing_count":12,"errors":[]},
                "gold_events":[
                    {"id":"a","counterparty":"A","event_type":"ACQUIRED",
                     "status":"COMPLETED","deepest_stage":"LOCATOR_CAPTURED",
                     "stages":{"filings_retrieved":True,"relevant_text_present":True,
                               "locator_captured":True,"entity_recognized":False,
                               "event_extracted":False,"candidate_emitted":False}},
                    {"id":"b","counterparty":"B","event_type":"ACQUIRED",
                     "status":"COMPLETED","deepest_stage":"CANDIDATE_EMITTED",
                     "stages":{"filings_retrieved":True,"relevant_text_present":True,
                               "locator_captured":True,"entity_recognized":True,
                               "event_extracted":True,"candidate_emitted":True}},
                ]}
            (Path(directory)/"x.json").write_text(json.dumps(data))
            result=summarize(study,directory)
        self.assertEqual(result["known_sentinel_events_evaluated"],2)
        self.assertEqual(result["counterparty_candidate_emitted_for_sentinel_events"],1)
        self.assertEqual(result["gold_events_extracted_for_sentinel_events"],1)
        self.assertEqual(result["fully_detected_sentinel_events"],1)
        self.assertEqual(result["sentinel_event_detection_fraction"],0.5)
        self.assertEqual(result["companies"][0]["events"][0]["first_unpassed_stage"],
                         "entity_recognized")

    def test_counterparty_emitted_without_gold_event_is_not_found(self):
        study={"study_id":"fixture","companies":[{"id":"x","company":"X","cik":"1"}]}
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory)/"x.json").write_text(json.dumps({
                "cik":"1",
                "retrieval":{"filing_count":4,"errors":[]},
                "gold_events":[{
                    "id":"historical",
                    "counterparty":"Bayer Aktiengesellschaft",
                    "stages":{
                        "filings_retrieved":True,
                        "relevant_text_present":True,
                        "locator_captured":True,
                        "entity_recognized":True,
                        "event_extracted":False,
                        "candidate_emitted":True
                    }
                }]
            }))
            result=summarize(study,directory)
        self.assertEqual(result["counterparty_candidate_emitted_for_sentinel_events"],1)
        self.assertEqual(result["gold_events_extracted_for_sentinel_events"],0)
        self.assertEqual(result["fully_detected_sentinel_events"],0)
        self.assertEqual(result["sentinel_event_detection_fraction"],0)
        event=result["companies"][0]["events"][0]
        self.assertFalse(event["found"])
        self.assertEqual(event["first_unpassed_stage"],"event_extracted")

    def test_retrieval_errors_preclude_clean_rate(self):
        study={"study_id":"fixture","companies":[{"id":"x","company":"X"}]}
        with tempfile.TemporaryDirectory() as directory:
            (Path(directory)/"x.json").write_text(json.dumps({
                "gold_events":[{"stages":{"candidate_emitted":False}}],
                "retrieval":{"errors":[{"error":"HTTP 429"}]}
            }))
            result=summarize(study,directory)
        self.assertIsNone(result["sentinel_event_detection_fraction"])
        self.assertEqual(result["retrieval_error_count"],1)

if __name__ == "__main__":
    unittest.main()
