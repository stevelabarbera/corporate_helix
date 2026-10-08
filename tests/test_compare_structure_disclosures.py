import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))

from compare_structure_disclosures import compare


def appearance(date, accession, name, jurisdiction):
    return {
        "filing_date": date,
        "accession": accession,
        "name": name,
        "jurisdiction": jurisdiction,
    }


def entity(key, *rows):
    return {"identity_key": key, "filing_appearances": list(rows)}


def test_reports_appearance_and_disappearance_without_event_inference():
    timeline = {
        "company": "Example Corp.",
        "cik": "1",
        "filing_dates": ["2020-01-01", "2021-01-01"],
        "entities": [
            entity("old llc", appearance("2020-01-01", "a", "Old LLC", "DE")),
            entity("new inc", appearance("2021-01-01", "b", "New, Inc.", "CA")),
        ],
    }

    result = compare(timeline)
    assert result["summary"]["counts_by_type"] == {
        "APPEARED_IN_DISCLOSURE": 1,
        "DISAPPEARED_FROM_DISCLOSURE": 1,
    }
    assert all(c["inferred_corporate_event"] is None for c in result["changes"])
    assert all(c["requires_external_confirmation"] for c in result["changes"])


def test_reports_reappearance_after_a_disclosure_gap():
    timeline = {
        "company": "Example Corp.",
        "cik": "1",
        "filing_dates": ["2020-01-01", "2021-01-01", "2022-01-01"],
        "entities": [entity(
            "returning inc",
            appearance("2020-01-01", "a", "Returning, Inc.", "DE"),
            appearance("2022-01-01", "c", "Returning, Inc.", "DE"),
        )],
    }

    result = compare(timeline)
    assert [c["change_type"] for c in result["changes"]] == [
        "DISAPPEARED_FROM_DISCLOSURE",
        "REAPPEARED_IN_DISCLOSURE",
    ]


def test_reports_text_changes_without_calling_them_legal_changes():
    timeline = {
        "company": "Example Corp.",
        "cik": "1",
        "filing_dates": ["2020-01-01", "2021-01-01"],
        "entities": [entity(
            "example inc",
            appearance("2020-01-01", "a", "Example Inc", "Delaware"),
            appearance("2021-01-01", "b", "Example, Inc.", "DE"),
        )],
    }

    result = compare(timeline)
    assert [c["change_type"] for c in result["changes"]] == [
        "NAME_TEXT_CHANGED",
        "JURISDICTION_TEXT_CHANGED",
    ]
    assert "disclosure only" in result["interpretation_warning"]
