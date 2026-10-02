from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))

import fetch_edgar_v4
from fetch_edgar_v4 import annual_filings, extract_exhibit_21_rows, is_exhibit_21_filename
from providers.edgar_adapter import EdgarJsonAdapter


TARGET_FLAT_EXHIBIT = """
<html><body>
  <p>Exhibit 21.1</p>
  <p>Target Corporation</p>
  <p>(A Minnesota Corporation)</p>
  <p>List of Significant Subsidiaries</p>
  <p>(As of February 1, 2025)</p>
  <p>Target Brands, Inc. (MN)</p>
  <p>Target Enterprise, Inc. (MN)</p>
  <p>Target General Merchandise, Inc. (MN)</p>
  <p>Pursuant to Item 601(b)(21)(ii), names of other subsidiaries are omitted.</p>
</body></html>
"""


def test_flat_exhibit_21_extracts_only_list_entities():
    assert extract_exhibit_21_rows(TARGET_FLAT_EXHIBIT) == [
        ["Subsidiary", "State/Country of Organization"],
        ["Target Brands, Inc.", "MN"],
        ["Target Enterprise, Inc.", "MN"],
        ["Target General Merchandise, Inc.", "MN"],
    ]


def test_flat_exhibit_21_flows_through_edgar_adapter():
    rows = extract_exhibit_21_rows(TARGET_FLAT_EXHIBIT)
    result = EdgarJsonAdapter().from_dict(
        {
            "company": "Target Corporation",
            "cik": "27419",
            "filings": [{
                "accession": "0000027419-25-000018",
                "filing_date": "2025-03-12",
                "form_type": "10-K",
                "document_url": "https://www.sec.gov/example-ex21.htm",
                "extraction_method": "exhibit_21",
                "extracted_rows": rows,
            }],
        },
        "Target Corporation",
    )

    assert [e.legal_name for e in result.entities] == [
        "Target Brands, Inc.",
        "Target Enterprise, Inc.",
        "Target General Merchandise, Inc.",
    ]
    assert {r.predicate for r in result.relationships} == {"HAS_SUBSIDIARY"}
    assert {r.jurisdiction for r in result.relationships} == {"MN"}
    assert all(
        r.evidence[0].coverage == "exhibit_21_disclosed_entities"
        for r in result.relationships
    )


def test_table_exhibit_21_behavior_is_preserved():
    table = """
    <table>
      <tr><th>Subsidiary</th><th>Jurisdiction</th></tr>
      <tr><td>Shipt, Inc.</td><td>Delaware</td></tr>
    </table>
    """
    assert extract_exhibit_21_rows(table) == [
        ["Subsidiary", "Jurisdiction"],
        ["Shipt, Inc.", "Delaware"],
    ]


def test_exhibit_21_filename_variants_are_recognized():
    assert is_exhibit_21_filename("ex-21.htm")
    assert is_exhibit_21_filename("exhibit21.1.html")
    assert is_exhibit_21_filename("tgt-20250201xexhibit211.htm")
    assert not is_exhibit_21_filename("exhibit10.htm")
    assert not is_exhibit_21_filename("annual-report.htm")


def test_historical_filing_year_reads_matching_sec_archive(monkeypatch):
    current = {
        "filings": {
            "recent": {
                "form": ["10-K"],
                "accessionNumber": ["current-accession"],
                "filingDate": ["2026-03-11"],
                "primaryDocument": ["current.htm"],
            },
            "files": [{
                "name": "CIK0000027419-submissions-001.json",
                "filingFrom": "1994-01-01",
                "filingTo": "2015-12-31",
            }],
        }
    }
    archived = {
        "form": ["10-Q", "10-K", "10-K"],
        "accessionNumber": ["quarterly", "target-2011", "target-2010"],
        "filingDate": ["2011-11-01", "2011-03-11", "2010-03-12"],
        "primaryDocument": ["q.htm", "annual-2011.htm", "annual-2010.htm"],
    }

    def fake_get_json(url, _user_agent):
        if url.endswith("CIK0000027419.json"):
            return current
        if url.endswith("CIK0000027419-submissions-001.json"):
            return archived
        raise AssertionError(url)

    monkeypatch.setattr(fetch_edgar_v4, "get_json", fake_get_json)

    assert annual_filings("27419", "test-agent", filing_year=2011) == [
        ("10-K", "target-2011", "2011-03-11", "annual-2011.htm")
    ]


def test_latest_filing_path_does_not_fetch_archives(monkeypatch):
    calls = []
    current = {
        "filings": {
            "recent": {
                "form": ["10-K"],
                "accessionNumber": ["current-accession"],
                "filingDate": ["2026-03-11"],
                "primaryDocument": ["current.htm"],
            },
            "files": [{
                "name": "CIK0000027419-submissions-001.json",
                "filingFrom": "1994-01-01",
                "filingTo": "2015-12-31",
            }],
        }
    }

    def fake_get_json(url, _user_agent):
        calls.append(url)
        return current

    monkeypatch.setattr(fetch_edgar_v4, "get_json", fake_get_json)

    assert annual_filings("27419", "test-agent") == [
        ("10-K", "current-accession", "2026-03-11", "current.htm")
    ]
    assert len(calls) == 1
