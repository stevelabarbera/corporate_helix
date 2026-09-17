import importlib.util
from pathlib import Path

P = Path(__file__).resolve().parents[1] / "code/eval/run_ma_s1_baseline.py"
spec = importlib.util.spec_from_file_location("ma_s1", P)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def test_analyze_event_distinguishes_locator_from_entity_failure():
    gold = {"id": "x-1", "counterparty": "Target, Inc."}
    filings = [{"accession": "a1", "raw_text": "We acquired Target, Inc."}]
    event = m.analyze_event(gold, filings, [], [])
    assert event["stages"]["relevant_text_present"] is True
    assert event["stages"]["locator_captured"] is False
    assert event["deepest_stage"] == "RELEVANT_TEXT_PRESENT"


def test_event_extraction_is_distinct_from_provider_pivot_linkage():
    gold = {
        "id": "x-1", "counterparty": "Target, Inc.",
        "event_type": "ACQUIRED", "status": "COMPLETED",
    }
    filing = {"accession": "a1", "raw_text": "Buyer acquired Target, Inc."}
    section = {"item": "2.01", "text": filing["raw_text"]}
    parsed = {
        "fused": {"orgs": ["Target, Inc."]},
        "completed_events": [{
            "subject": "Historical Buyer, Inc.", "object": "Target, Inc.",
            "event_type": "ACQUIRED", "status": "COMPLETED", "extraction_rule": "X",
        }],
    }
    event = m.analyze_event(
        gold, [filing],
        [{"filing": filing, "section": section, "parsed": parsed, "pivot_name": "Current Buyer, Inc."}],
        [],
    )
    assert event["stages"]["event_extracted"] is True
    assert event["stages"]["candidate_emitted"] is False
    assert event["deepest_stage"] == "EVENT_EXTRACTED"
    assert event["evidence"]["event_hits"][0]["provider_other_party"] is None


def test_event_extraction_requires_gold_event_type():
    gold = {
        "id": "x-1", "counterparty": "Target, Inc.",
        "event_type": "AGREED_TO_ACQUIRE", "status": "COMPLETED",
    }
    filing = {"accession": "a1", "raw_text": "Buyer acquired Target, Inc."}
    section = {"item": "2.01", "text": filing["raw_text"]}
    parsed = {
        "fused": {"orgs": ["Target, Inc."]},
        "completed_events": [{
            "subject": "Buyer, Inc.", "object": "Target, Inc.",
            "event_type": "ACQUIRED", "status": "COMPLETED", "extraction_rule": "X",
        }],
    }
    event = m.analyze_event(
        gold, [filing],
        [{"filing": filing, "section": section, "parsed": parsed, "pivot_name": "Buyer, Inc."}],
        [],
    )
    assert event["stages"]["entity_recognized"] is True
    assert event["stages"]["event_extracted"] is False
    assert event["deepest_stage"] == "ENTITY_RECOGNIZED"


def test_run_baseline_emits_durable_stage_record(monkeypatch):
    raw = "Registrant Corp. completed its acquisition of Target, Inc."
    section = {"item": "2.01", "text": raw}
    filings = [{
        "accession": "a1", "filing_date": "2024-01-01", "form": "8-K",
        "items": "2.01", "primary_document": "x.htm", "document_url": "https://example/x",
        "raw_text": raw, "sections": [section],
    }]

    class FakeProvider:
        def __init__(self, fetch_filings_fn):
            self.fetch = fetch_filings_fn

        def _parse_filing_section(self, text, item):
            return {
                "fused": {"orgs": ["Target, Inc."], "org_votes": {}, "aliases": {}},
                "ensemble": {},
                "completed_events": [{
                    "subject": "REGISTRANT_SELF_REFERENCE", "object": "Target, Inc.",
                    "event_type": "ACQUIRED", "status": "COMPLETED",
                    "extraction_rule": "DECLARATIVE_ACQUISITION", "evidence": text,
                }],
            }

        def __call__(self, pivot, iteration):
            from iterative_expansion import HelixFact
            return [HelixFact(
                fact_type="LEGAL_ENTITY", value="Target, Inc.", identifier=None,
                source="EDGAR_MA", confidence="MEDIUM", status="REVIEW",
                pivot_eligible=False,
            )]

    monkeypatch.setattr(m, "git_head", lambda: "abc123")
    result = m.run_baseline(
        {"id": "issuer", "company": "Registrant Corp."},
        {"events": [{"id": "issuer-1", "counterparty": "Target, Inc."}]},
        user_agent="test test@example.com", start="2020-01-01", end="2026-12-31",
        resolve_fn=lambda name, ua: "0000000001",
        collector=lambda *a, **k: ("0000000001", filings, []),
        provider_factory=FakeProvider,
    )
    event = result["gold_events"][0]
    assert all(event["stages"].values())
    assert event["deepest_stage"] == "CANDIDATE_EMITTED"
    assert result["observed_primitives"] == [
        "EXTRACTION_RULE:DECLARATIVE_ACQUISITION", "FORM:8-K", "SECTION:2.01",
    ]
    assert result["failure_classes"] == []
    assert result["baseline_commit"] == "abc123"


def test_collect_audit_filings_retains_raw_text_when_locator_misses():
    submissions = {"filings": {"recent": {
        "form": ["10-K"], "filingDate": ["2024-02-01"],
        "accessionNumber": ["0000000001-24-000001"], "primaryDocument": ["annual.htm"],
    }}}
    cik, filings, errors = m.collect_audit_filings(
        "1", "test test@example.com", start="2020-01-01", end="2026-12-31",
        load_submissions_fn=lambda cik, ua: ("0000000001", submissions),
        get_text_fn=lambda url, ua: "<p>No transaction language here.</p>",
    )
    assert cik == "0000000001" and not errors
    assert filings[0]["raw_text"] == "No transaction language here."
    assert filings[0]["sections"] == []
