import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))

from build_structure_disclosure_timeline import build


def filing(date, accession, rows):
    return {
        "filing_date": date,
        "accession": accession,
        "form_type": "10-K",
        "document_url": f"https://www.sec.gov/{accession}",
        "extraction_method": "exhibit_21",
        "extracted_rows": [
            ["Subsidiary", "State/Country of Organization"],
            *rows,
        ],
    }


def test_builds_disclosure_bounds_without_claiming_legal_end_dates():
    raw = {
        "company": "Target Corporation",
        "cik": "27419",
        "filings": [
            filing("2020-03-11", "a", [["Target Brands, Inc.", "MN"]]),
            filing("2021-03-10", "b", [["Shipt, Inc.", "DE"]]),
            filing("2022-03-09", "c", [["Target Brands, Inc", "Minnesota"]]),
        ],
    }

    timeline = build(raw)
    assert timeline["summary"] == {"entity_count": 2, "observation_count": 3}
    brands = next(e for e in timeline["entities"] if e["identity_key"] == "target brands inc")
    assert brands["aliases"] == ["Target Brands, Inc", "Target Brands, Inc."]
    assert brands["first_observed"] == "2020-03-11"
    assert brands["last_observed"] == "2022-03-09"
    assert brands["not_disclosed_between_observations"] == ["2021-03-10"]
    assert brands["current_filing_disclosure"] is True
    assert "does not prove" in timeline["interpretation_warning"]


def test_missing_after_last_observation_is_not_an_inferred_divestiture():
    raw = {
        "company": "Target Corporation",
        "cik": "27419",
        "filings": [
            filing("2020-03-11", "a", [["Target Capital Corporation", "MN"]]),
            filing("2021-03-10", "b", []),
        ],
    }

    entity = build(raw)["entities"][0]
    assert entity["last_observed"] == "2020-03-11"
    assert entity["current_filing_disclosure"] is False
    assert "last_seen" not in entity


def test_legal_forms_are_not_collapsed_into_one_entity():
    raw = {
        "company": "Target Corporation",
        "cik": "27419",
        "filings": [
            filing("2020-03-11", "a", [["Target Receivables Corporation", "MN"]]),
            filing("2021-03-10", "b", [["Target Receivables LLC", "MN"]]),
            filing("2022-03-09", "c", [
                ["Target Sourcing Services Co., Ltd.", "Shanghai"],
                ["Target Sourcing Services Limited", "Hong Kong"],
            ]),
        ],
    }

    timeline = build(raw)
    assert timeline["summary"]["entity_count"] == 4
    assert {e["identity_key"] for e in timeline["entities"]} == {
        "target receivables corporation",
        "target receivables llc",
        "target sourcing services co ltd",
        "target sourcing services limited",
    }
