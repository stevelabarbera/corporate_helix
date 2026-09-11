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


def test_other_party_returns_the_non_pivot_side():
    event = {"subject": "Cisco Systems, Inc.", "object": "Splunk Inc.", "status": "COMPLETED"}
    assert other_party(event, "Cisco Systems, Inc.") == "Splunk Inc."
    assert other_party(event, "Splunk Inc.") == "Cisco Systems, Inc."


def test_other_party_returns_none_when_ambiguous():
    # Both sides match (or neither does) -- must not guess.
    event = {"subject": "Acme Inc.", "object": "Acme Inc.", "status": "COMPLETED"}
    assert other_party(event, "Acme Inc.") is None
    event2 = {"subject": "Foo Inc.", "object": "Bar Inc.", "status": "COMPLETED"}
    assert other_party(event2, "Unrelated Corp.") is None


def test_real_cisco_filing_discovers_splunk():
    data = json.loads((RAW_DIR / "edgar_cisco_events_v3831.json").read_text())
    provider = EdgarMAExpansionProvider(fetch_filings_fn=lambda p: data)
    facts = list(provider(_pivot("Cisco Systems, Inc."), 1))
    names = {f.value for f in facts}
    assert "Splunk Inc." in names
    splunk = next(f for f in facts if f.value == "Splunk Inc.")
    assert splunk.pivot_eligible is True
    assert splunk.fact_type == "LEGAL_ENTITY"
    assert len(splunk.evidence) >= 1


def test_real_broadcom_filing_discovers_vmware():
    data = json.loads((RAW_DIR / "edgar_broadcom_events_v3831.json").read_text())
    provider = EdgarMAExpansionProvider(fetch_filings_fn=lambda p: data)
    facts = list(provider(_pivot("Broadcom Inc."), 1))
    names = {f.value for f in facts}
    assert "VMware, Inc." in names


def test_edgar_has_nothing_returns_empty_not_error():
    provider = EdgarMAExpansionProvider(fetch_filings_fn=lambda p: None)
    facts = list(provider(_pivot("Some Private Company LLC"), 1))
    assert facts == []


def test_two_hop_recursion_through_run_expansion():
    # Real Cisco data for hop 1; a synthetic Splunk filing for hop 2, to prove
    # a newly-discovered LEGAL_ENTITY fact actually re-enters the frontier and
    # gets the same treatment, not just a one-shot lookup.
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
        return None  # Acme Telemetry: not a public filer -- natural termination

    provider = EdgarMAExpansionProvider(fetch_filings_fn=fixture_fetch)
    result = run_expansion([_pivot("Cisco Systems, Inc.")], [provider], max_iterations=5)

    assert result.converged is True
    names = {f.value for f in result.facts}
    assert names == {"Cisco Systems, Inc.", "Splunk Inc.", "Acme Telemetry, Inc."}


def test_recursion_terminates_when_nothing_new_found():
    # Guard against infinite loops: if EDGAR has nothing for anyone, expansion
    # must converge immediately, not error or hang.
    provider = EdgarMAExpansionProvider(fetch_filings_fn=lambda p: None)
    result = run_expansion([_pivot("Nobody Files Anything Inc.")], [provider], max_iterations=10)
    assert result.converged is True
    assert result.iterations_run <= 1
