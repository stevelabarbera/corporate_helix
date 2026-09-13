#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))

from providers.edgar_ma_provider import EdgarMAExpansionProvider, other_party
from iterative_expansion import HelixFact, run_expansion

RAW_DIR = Path(__file__).resolve().parents[1] / "data" / "raw"


def _pivot(name: str) -> HelixFact:
    return HelixFact(
        fact_type="COMPANY", value=name, identifier=None,
        source="SEED", confidence="HIGH", status="ACCEPTED", pivot_eligible=True,
    )


def _authorize_all(event, pivot, evidence):
    # Test-only adjudication hook: proves the recursion mechanism still works
    # when a separate trust policy explicitly authorizes a parser candidate.
    return True


def test_other_party_returns_the_non_pivot_side():
    event = {"subject": "Cisco Systems, Inc.", "object": "Splunk Inc.", "status": "COMPLETED"}
    assert other_party(event, "Cisco Systems, Inc.") == "Splunk Inc."
    assert other_party(event, "Splunk Inc.") == "Cisco Systems, Inc."


def test_other_party_returns_none_when_ambiguous():
    event = {"subject": "Acme Inc.", "object": "Acme Inc.", "status": "COMPLETED"}
    assert other_party(event, "Acme Inc.") is None
    event2 = {"subject": "Foo Inc.", "object": "Bar Inc.", "status": "COMPLETED"}
    assert other_party(event2, "Unrelated Corp.") is None


def test_real_cisco_filing_discovers_splunk_as_review_candidate():
    data = json.loads((RAW_DIR / "edgar_cisco_events_v3831.json").read_text())
    provider = EdgarMAExpansionProvider(fetch_filings_fn=lambda p: data)
    facts = list(provider(_pivot("Cisco Systems, Inc."), 1))

    splunk = next(f for f in facts if f.value == "Splunk Inc.")
    assert splunk.fact_type == "LEGAL_ENTITY"
    assert splunk.status == "REVIEW"
    assert splunk.confidence == "MEDIUM"
    assert splunk.pivot_eligible is False
    assert len(splunk.evidence) >= 1


def test_real_broadcom_filing_discovers_vmware_as_review_candidate():
    data = json.loads((RAW_DIR / "edgar_broadcom_events_v3831.json").read_text())
    provider = EdgarMAExpansionProvider(fetch_filings_fn=lambda p: data)
    facts = list(provider(_pivot("Broadcom Inc."), 1))
    vmware = next(f for f in facts if f.value == "VMware, Inc.")
    assert vmware.status == "REVIEW"
    assert vmware.pivot_eligible is False


def test_edgar_evidence_preserves_event_provenance():
    data = json.loads((RAW_DIR / "edgar_cisco_events_v3831.json").read_text())
    provider = EdgarMAExpansionProvider(fetch_filings_fn=lambda p: data)
    facts = list(provider(_pivot("Cisco Systems, Inc."), 1))
    splunk = next(f for f in facts if f.value == "Splunk Inc.")
    ev = splunk.evidence[0]

    assert ev["accession"]
    assert ev["event_type"]
    assert ev["subject"]
    assert ev["object"]
    assert ev["source_text"]
    assert ev["extraction_rule"]
    assert ev["section_sha256"]
    assert ev["parser_ensemble"]["mode"] == "VALIDATED_3_BACKEND"
    assert ev["trust_decision"] == "PARSER_CANDIDATE_REQUIRES_ADJUDICATION"


def test_edgar_has_nothing_returns_empty_not_error():
    provider = EdgarMAExpansionProvider(fetch_filings_fn=lambda p: None)
    facts = list(provider(_pivot("Some Private Company LLC"), 1))
    assert facts == []


def test_default_parser_candidate_does_not_recursively_pivot():
    real_cisco = json.loads((RAW_DIR / "edgar_cisco_events_v3831.json").read_text())
    synthetic_splunk = {
        "company": "Splunk Inc.", "cik": "9999999999",
        "filings": [{
            "accession": "0000000000-00-000001", "filing_date": "2019-05-01",
            "form": "8-K", "items": "2.01",
            "sections": [{"item": "2.01", "text": (
                'Splunk Inc. ("Splunk") today announced that it has completed its '
                'acquisition of Acme Telemetry, Inc. ("Acme Telemetry"), pursuant to '
                "the previously announced Agreement and Plan of Merger."
            )}],
        }],
    }

    def fixture_fetch(pivot):
        if "cisco" in pivot.value.casefold():
            return real_cisco
        if "splunk" in pivot.value.casefold():
            return synthetic_splunk
        return None

    provider = EdgarMAExpansionProvider(fetch_filings_fn=fixture_fetch)
    result = run_expansion([_pivot("Cisco Systems, Inc.")], [provider], max_iterations=5)

    names = {f.value for f in result.facts}
    assert "Splunk Inc." in names
    assert "Acme Telemetry, Inc." not in names


def test_two_hop_recursion_requires_explicit_authorization():
    real_cisco = json.loads((RAW_DIR / "edgar_cisco_events_v3831.json").read_text())
    synthetic_splunk = {
        "company": "Splunk Inc.", "cik": "9999999999",
        "filings": [{
            "accession": "0000000000-00-000001", "filing_date": "2019-05-01",
            "form": "8-K", "items": "2.01",
            "sections": [{"item": "2.01", "text": (
                'Splunk Inc. ("Splunk") today announced that it has completed its '
                'acquisition of Acme Telemetry, Inc. ("Acme Telemetry"), pursuant to '
                "the previously announced Agreement and Plan of Merger."
            )}],
        }],
    }

    def fixture_fetch(pivot):
        if "cisco" in pivot.value.casefold():
            return real_cisco
        if "splunk" in pivot.value.casefold():
            return synthetic_splunk
        return None

    provider = EdgarMAExpansionProvider(
        fetch_filings_fn=fixture_fetch,
        authorize_pivot_fn=_authorize_all,
    )
    result = run_expansion([_pivot("Cisco Systems, Inc.")], [provider], max_iterations=5)

    assert result.converged is True
    names = {f.value for f in result.facts}
    assert names == {"Cisco Systems, Inc.", "Splunk Inc.", "Acme Telemetry, Inc."}


def test_real_10k_filing_discovers_two_review_candidates_end_to_end():
    tenk_text = (
        'In October 2023, we acquired Ermetic Ltd. ("Ermetic"), an innovative cloud-native '
        "application protection platform company. We acquired 100% of Ermetic equity through "
        "a share purchase agreement for total consideration of $243.8 million.\n\n"
        'In June 2022, we acquired Bit Discovery, Inc. ("Bit Discovery"), a leader in external '
        "attack surface management. We acquired 100% of Bit Discovery equity for $43.8 million in cash."
    )
    data = {
        "company": "Tenable Holdings, Inc.", "cik": "0001660280",
        "filings": [{
            "accession": "0001660280-24-000033",
            "filing_date": "2024-02-28",
            "form": "10-K",
            "items": "",
            "sections": [{"item": "NOTES", "text": tenk_text}],
        }],
    }
    provider = EdgarMAExpansionProvider(fetch_filings_fn=lambda p: data)
    facts = list(provider(_pivot("Tenable Holdings, Inc."), 1))
    assert {f.value for f in facts} == {"Ermetic Ltd.", "Bit Discovery, Inc."}
    assert all(f.status == "REVIEW" and not f.pivot_eligible for f in facts)


def test_recursion_terminates_when_nothing_new_found():
    provider = EdgarMAExpansionProvider(fetch_filings_fn=lambda p: None)
    result = run_expansion([_pivot("Nobody Files Anything Inc.")], [provider], max_iterations=10)
    assert result.converged is True
    assert result.iterations_run <= 1
