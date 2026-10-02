from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))

from fetch_edgar_v4 import extract_exhibit_21_rows
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
