#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))

from iterative_expansion import HelixFact
from providers.edgar_ma_provider import EdgarMAExpansionProvider


def _pivot(name: str) -> HelixFact:
    return HelixFact(
        fact_type="COMPANY",
        value=name,
        identifier=None,
        source="SEED",
        confidence="HIGH",
        status="ACCEPTED",
        pivot_eligible=True,
    )


def test_longform_locator_provenance_survives_into_helix_evidence():
    text = (
        'In October 2023, we acquired Ermetic Ltd. ("Ermetic"). '
        "We acquired 100% of Ermetic equity for total consideration."
    )
    data = {
        "company": "Tenable Holdings, Inc.",
        "cik": "0001660280",
        "filings": [{
            "accession": "0001660280-24-000033",
            "filing_date": "2024-02-28",
            "form": "10-K",
            "primary_document": "tenable-20231231.htm",
            "document_url": "https://example.test/tenable-20231231.htm",
            "sections": [{
                "item": "LONGFORM_MA_CANDIDATE",
                "text": text,
                "start_char": 4000,
                "end_char": 4000 + len(text),
                "locator_version": "EDGAR_LONGFORM_MA_V1",
                "locator_terms": ["ACQUIRE"],
                "locator_hits": [{"kind": "ACQUIRE", "term": "acquired", "start": 4019, "end": 4027}],
                "region_number": 3,
            }],
        }],
    }

    provider = EdgarMAExpansionProvider(fetch_filings_fn=lambda p: data)
    facts = list(provider(_pivot("Tenable Holdings, Inc."), 1))

    ermetic = next(f for f in facts if f.value == "Ermetic Ltd.")
    ev = ermetic.evidence[0]

    assert ev["locator_version"] == "EDGAR_LONGFORM_MA_V1"
    assert ev["locator_region_number"] == 3
    assert ev["locator_start_char"] == 4000
    assert ev["locator_end_char"] == 4000 + len(text)
    assert "ACQUIRE" in ev["locator_terms"]
    assert ev["trust_decision"] == "PARSER_CANDIDATE_REQUIRES_ADJUDICATION"
    assert ermetic.status == "REVIEW"
    assert ermetic.pivot_eligible is False
