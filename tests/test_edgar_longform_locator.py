#!/usr/bin/env python3
from __future__ import annotations
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))
from parsers.edgar_longform_locator import LOCATOR_VERSION, locate_ma_regions
import providers.edgar_resolver as resolver

def test_locator_returns_nothing_for_unrelated_long_form_text():
    assert locate_ma_regions("Risk Factors\nWe invest in research and development.", form="10-K") == []

def test_locator_finds_scattered_acquisition_evidence_document_wide():
    text = "A"*2500 + "\nWe acquired Ermetic Ltd. for cash.\n" + "B"*5000 + "\nWe acquired Bit Discovery, Inc. through a share purchase agreement.\n" + "C"*2500
    regions = locate_ma_regions(text, form="10-K", before_chars=300, after_chars=500, merge_gap_chars=50)
    assert len(regions) == 2
    assert "Ermetic Ltd." in regions[0]["text"]
    assert "Bit Discovery, Inc." in regions[1]["text"]
    assert all(r["locator_version"] == LOCATOR_VERSION for r in regions)
    assert all("ACQUIRE" in r["locator_terms"] for r in regions)

def test_locator_merges_nearby_signal_windows():
    text = "We acquired Example One, Inc. The acquisition was accounted for as a business combination. Purchase price allocation is preliminary."
    regions = locate_ma_regions(text, form="10-K", before_chars=50, after_chars=80, merge_gap_chars=50)
    assert len(regions) == 1
    assert {"ACQUIRE", "ACQUISITION", "BUSINESS_COMBINATION", "PURCHASE_PRICE"} <= set(regions[0]["locator_terms"])

def test_locator_is_reusable_for_10q_without_a_second_parser():
    regions = locate_ma_regions("During the quarter, we acquired Example Cloud, Inc.", form="10-Q")
    assert len(regions) == 1
    assert regions[0]["form"] == "10-Q"

def test_combined_fetch_reads_submissions_once_and_returns_8k_plus_10k(monkeypatch):
    submissions = {"name":"Example Holdings, Inc.","filings":{"recent":{
        "form":["8-K","10-K"],"filingDate":["2024-01-10","2024-02-28"],"items":["2.01",""],
        "accessionNumber":["0000000001-24-000001","0000000001-24-000002"],
        "primaryDocument":["example-8k.htm","example-10k.htm"]}}}
    calls = []
    monkeypatch.setattr(resolver, "_get_json", lambda url, ua: (calls.append(url) or submissions))
    def fake_text(url, ua):
        if url.endswith("example-8k.htm"):
            return "<div>Item 2.01 Completion</div><p>Example Holdings, Inc. completed its acquisition of Target Systems, Inc.</p>"
        return "<p>Note 7. Acquisitions</p><p>In October 2023, we acquired Ermetic Ltd. for total consideration.</p>"
    monkeypatch.setattr(resolver, "_get_text", fake_text)
    data = resolver.fetch_ma_filings("1", "test@example.com")
    assert len(calls) == 1
    assert {f["form"] for f in data["filings"]} == {"8-K","10-K"}
    tenk = next(f for f in data["filings"] if f["form"] == "10-K")
    assert tenk["longform_locator"] is True
    assert tenk["sections"][0]["locator_version"] == LOCATOR_VERSION
    assert "Ermetic Ltd." in tenk["sections"][0]["text"]
