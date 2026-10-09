import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))

from collect_structure_change_evidence import (
    collect, filing_documents, filing_metadata, relevant_passages, select_change,
)


CHANGE = {
    "change_type": "DISAPPEARED_FROM_DISCLOSURE",
    "identity_key": "example subsidiary inc",
    "previous_filing_date": "2020-03-01",
    "current_filing_date": "2021-03-01",
    "previous_disclosure": {"names": ["Example Subsidiary, Inc."]},
    "current_disclosure": None,
}


def test_historical_metadata_uses_overlapping_archive_and_filters_window():
    current = {"filings": {"recent": {
        "form": ["10-K"], "filingDate": ["2026-03-01"],
        "accessionNumber": ["recent"], "primaryDocument": ["recent.htm"], "items": [""],
    }, "files": [{
        "name": "old.json", "filingFrom": "2019-01-01", "filingTo": "2021-12-31",
    }]}}
    archived = {
        "form": ["8-K", "10-Q", "DEF 14A"],
        "filingDate": ["2020-08-01", "2021-02-01", "2020-09-01"],
        "accessionNumber": ["a", "b", "c"],
        "primaryDocument": ["a.htm", "b.htm", "c.htm"],
        "items": ["2.01", "", ""],
    }
    def loader(url, _ua):
        return archived if url.endswith("old.json") else current

    rows = filing_metadata("1", "agent", "2020-03-01", "2021-03-01", json_loader=loader)
    assert [row["accession"] for row in rows] == ["a", "b"]


def test_passages_match_punctuation_variants_and_ignore_unrelated_text():
    text = "Unrelated beginning. Example Subsidiary Inc completed a transaction. Ending."
    passages = relevant_passages(text, ["Example Subsidiary, Inc."], radius=10)
    assert len(passages) == 1
    assert "Example Subsidiary Inc" in passages[0]["text"]
    assert passages[0]["matched_terms"] == ["Example Subsidiary, Inc."]


def test_collect_builds_pending_packet_with_stable_evidence_id():
    current = {"filings": {"recent": {
        "form": ["8-K"], "filingDate": ["2020-08-01"],
        "accessionNumber": ["0001-20-000001"], "primaryDocument": ["event.htm"],
        "items": ["2.01"],
    }, "files": []}}
    def json_loader(_url, _ua): return current
    def text_loader(_url, _ua):
        return "<p>Example Subsidiary, Inc. was sold on July 31, 2020.</p>"

    first = collect(CHANGE, "1", "agent", json_loader=json_loader, text_loader=text_loader)
    second = collect(CHANGE, "1", "agent", json_loader=json_loader, text_loader=text_loader)
    assert first["adjudication"]["status"] == "PENDING"
    assert first["collection"]["evidence_passage_count"] == 1
    assert first["evidence"][0]["evidence_id"] == second["evidence"][0]["evidence_id"]
    assert first["evidence"][0]["form"] == "8-K"


def test_filing_package_includes_relevant_exhibits_but_not_unrelated_files():
    filing = {
        "accession": "0001-20-000001", "primary_document": "report.htm",
    }
    index = {"directory": {"item": [
        {"name": "report.htm"},
        {"name": "ex-21.htm"},
        {"name": "company-exhibit991.htm"},
        {"name": "logo.jpg"},
        {"name": "cal.xml"},
    ]}}
    docs = filing_documents("1", filing, "agent", json_loader=lambda _u, _a: index)
    assert [d["document"] for d in docs] == [
        "report.htm", "ex-21.htm", "company-exhibit991.htm",
    ]
    assert [d["document_role"] for d in docs] == [
        "PRIMARY", "RELEVANT_EXHIBIT", "RELEVANT_EXHIBIT",
    ]


def test_select_change_requires_date_when_entity_has_multiple_changes():
    changes = {"changes": [
        {"identity_key": "x", "previous_filing_date": "2020-01-01"},
        {"identity_key": "x", "previous_filing_date": "2022-01-01"},
    ]}
    with pytest.raises(ValueError, match="Multiple changes"):
        select_change(changes, "x")
    assert select_change(changes, "x", "2022-01-01")["previous_filing_date"] == "2022-01-01"


def test_document_failure_is_recorded_without_losing_other_evidence():
    current = {"filings": {"recent": {
        "form": ["8-K"], "filingDate": ["2020-08-01"],
        "accessionNumber": ["0001-20-000001"], "primaryDocument": ["event.htm"],
        "items": ["2.01"],
    }, "files": []}}
    index = {"directory": {"item": [{"name": "ex-21.htm"}]}}
    def json_loader(url, _ua): return index if url.endswith("index.json") else current
    def text_loader(url, _ua):
        if url.endswith("event.htm"):
            raise OSError("temporary failure")
        return "Example Subsidiary Inc. was sold."

    packet = collect(CHANGE, "1", "agent", json_loader=json_loader, text_loader=text_loader)
    assert packet["collection"]["collection_error_count"] == 1
    assert packet["collection"]["evidence_passage_count"] == 1
