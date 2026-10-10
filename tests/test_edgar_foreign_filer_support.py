#!/usr/bin/env python3
"""
Foreign-private-issuer support (ADR-EDGAR-012).

Trigger: Einride AB (Swedish, Nasdaq: ENRD, CIK 2095096) disclosed its
July 2026 merger agreement to acquire Flipturn, Inc. in a Form 6-K
(accession 0001493152-26-034002). Before this change Helix retrieved
nothing for that issuer: the form allowlist was 8-K/10-K only, 6-Ks carry
no Item numbers to pre-filter on, "AB" was not a recognized corporate
form, and only filings.recent was read from the submissions metadata.

Network is monkeypatched throughout. The extractor passage below is
RECONSTRUCTED from sentences quoted out of the 6-K, not the verbatim
filing text -- it pins the intended grammar behavior, and should be
replaced by the real text once it is saved under data/raw/.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))

import providers.edgar_resolver as resolver
from providers.edgar_resolver import identity_key
from parsers.edgar_ma_extractor import EdgarMAExtractor


# --------------------------------------------------------------------- AB form

def test_ab_and_publ_are_corporate_form_words():
    assert identity_key("Einride") == identity_key("Einride AB") == "einride"
    assert identity_key("Einride AB (publ)") == "einride"


def test_ab_prefix_form_also_normalizes():
    # Swedish names are written both ways: "Volvo AB" and "AB Volvo".
    assert identity_key("AB Volvo") == identity_key("Volvo AB") == "volvo"


def test_ab_stripping_does_not_touch_words_that_merely_contain_ab():
    assert identity_key("Cabot Corporation") == "cabot"
    assert identity_key("Abbott Laboratories") == "abbott laboratories"
    assert identity_key("Fabrinet") == "fabrinet"


# ---------------------------------------------------------------- form families

def _submissions(forms, dates, items=None, docs=None):
    n = len(forms)
    return {"name": "Example AB", "filings": {"recent": {
        "form": forms, "filingDate": dates,
        "items": items or [""] * n,
        "accessionNumber": [f"0000000001-26-{i:06d}" for i in range(n)],
        "primaryDocument": docs or [f"doc{i}.htm" for i in range(n)],
    }}}


MERGER_6K = (
    "<p>On July 16, 2026, Example AB (the “Company”) entered into an Agreement and Plan "
    "of Merger with Example Merger Sub, Inc. and Target Software, Inc.</p>"
)


def test_6k_is_retrieved_through_the_locator_despite_having_no_items(monkeypatch):
    subs = _submissions(["6-K", "6-K"], ["2026-07-21", "2026-07-22"],
                        docs=["merger6k.htm", "boring6k.htm"])
    monkeypatch.setattr(resolver, "_get_json", lambda url, ua: subs)
    monkeypatch.setattr(resolver, "_get_text", lambda url, ua:
                        MERGER_6K if url.endswith("merger6k.htm") else "<p>Quarterly dividend declared.</p>")
    data = resolver.fetch_ma_filings("1", "test@example.com")
    assert [f["form"] for f in data["filings"]] == ["6-K"]       # boring 6-K is dropped
    f = data["filings"][0]
    assert f["longform_locator"] is True
    assert "Agreement and Plan" in f["sections"][0]["text"]


def test_20f_and_40f_annual_reports_are_retrieved(monkeypatch):
    subs = _submissions(["20-F", "40-F", "10-Q"], ["2026-03-01", "2026-03-02", "2026-05-01"])
    monkeypatch.setattr(resolver, "_get_json", lambda url, ua: subs)
    monkeypatch.setattr(resolver, "_get_text", lambda url, ua: "<p>In 2025 we acquired Target Software, Inc.</p>")
    data = resolver.fetch_ma_filings("1", "test@example.com")
    assert {f["form"] for f in data["filings"]} == {"20-F", "40-F"}   # 10-Q is out of scope here


def test_8k_item_gate_is_unchanged(monkeypatch):
    # 8-Ks still pre-filter on Item 1.01/2.01 -- the new forms must not have
    # loosened that.
    subs = _submissions(["8-K", "8-K"], ["2026-01-05", "2026-01-06"], items=["5.02", "2.01"],
                        docs=["people.htm", "deal.htm"])
    fetched = []
    monkeypatch.setattr(resolver, "_get_json", lambda url, ua: subs)
    def fake_text(url, ua):
        fetched.append(url.rsplit("/", 1)[-1])
        return "<div>Item 2.01 Completion of Acquisition</div><p>Example, Inc. completed its acquisition of Target Software, Inc.</p>"
    monkeypatch.setattr(resolver, "_get_text", fake_text)
    data = resolver.fetch_ma_filings("1", "test@example.com")
    assert fetched == ["deal.htm"]                      # Item 5.02 8-K never downloaded
    assert [f["form"] for f in data["filings"]] == ["8-K"]


def test_study_harness_audits_the_same_forms_production_retrieves():
    from eval.run_ma_s1_baseline import AUDIT_FORMS
    assert {"6-K", "20-F", "40-F", "8-K", "10-K"} <= AUDIT_FORMS


# ------------------------------------------------------------------- pagination

def _page(accessions, dates, forms=None):
    n = len(accessions)
    return {"accessionNumber": accessions, "filingDate": dates,
            "form": forms or ["8-K"] * n, "primaryDocument": [f"{a}.htm" for a in accessions]}


def _paged_submissions():
    return {"name": "Big Filer Inc.", "filings": {
        "recent": {"accessionNumber": ["R1"], "filingDate": ["2026-02-01"], "form": ["8-K"],
                   "primaryDocument": ["r1.htm"], "items": ["2.01"]},
        "files": [
            {"name": "CIK0000000001-submissions-001.json", "filingFrom": "2020-01-01", "filingTo": "2025-12-31"},
            {"name": "CIK0000000001-submissions-002.json", "filingFrom": "1994-01-01", "filingTo": "2019-12-31"},
        ]}}


def test_older_pages_are_merged_and_stay_row_aligned(monkeypatch):
    pages = {"CIK0000000001-submissions-001.json": _page(["A1", "A2"], ["2024-03-01", "2021-06-01"])}
    calls = []
    def fake_get_json(url, ua):
        calls.append(url)
        return _paged_submissions() if url.endswith("CIK0000000001.json") else pages[url.rsplit("/", 1)[-1]]
    monkeypatch.setattr(resolver, "_get_json", fake_get_json)
    _, subs = resolver._load_submissions("1", "ua", start="2020-01-01", end="2026-12-31")
    recent = subs["filings"]["recent"]
    assert recent["accessionNumber"] == ["R1", "A1", "A2"]
    # Every column is the same length and row-aligned, including a column
    # ("items") the older page doesn't carry at all.
    assert {len(v) for v in recent.values()} == {3}
    assert recent["items"] == ["2.01", "", ""]
    assert recent["filingDate"][1] == "2024-03-01"


def test_pages_outside_the_requested_window_are_never_fetched(monkeypatch):
    calls = []
    def fake_get_json(url, ua):
        calls.append(url.rsplit("/", 1)[-1])
        return _paged_submissions() if url.endswith("CIK0000000001.json") else _page(["A1"], ["2024-03-01"])
    monkeypatch.setattr(resolver, "_get_json", fake_get_json)
    resolver._load_submissions("1", "ua", start="2020-01-01", end="2026-12-31")
    assert "CIK0000000001-submissions-002.json" not in calls      # 1994-2019 is outside the window
    assert "CIK0000000001-submissions-001.json" in calls


def test_no_extra_pages_means_exactly_one_request(monkeypatch):
    calls = []
    subs = _submissions(["8-K"], ["2026-01-01"])
    monkeypatch.setattr(resolver, "_get_json", lambda url, ua: (calls.append(url) or subs))
    resolver._load_submissions("1", "ua", start="2015-01-01", end="2026-12-31")
    assert len(calls) == 1


def test_duplicate_accessions_across_pages_are_dropped(monkeypatch):
    def fake_get_json(url, ua):
        return _paged_submissions() if url.endswith("CIK0000000001.json") else _page(["R1", "A1"], ["2026-02-01", "2024-03-01"])
    monkeypatch.setattr(resolver, "_get_json", fake_get_json)
    _, subs = resolver._load_submissions("1", "ua", start="2020-01-01", end="2026-12-31")
    assert subs["filings"]["recent"]["accessionNumber"] == ["R1", "A1"]


def test_older_filings_flow_through_to_fetch_ma_filings(monkeypatch):
    pages = {"CIK0000000001-submissions-001.json": _page(["A1"], ["2023-04-01"], forms=["6-K"])}
    def fake_get_json(url, ua):
        return _paged_submissions() if url.endswith("CIK0000000001.json") else pages[url.rsplit("/", 1)[-1]]
    monkeypatch.setattr(resolver, "_get_json", fake_get_json)
    monkeypatch.setattr(resolver, "_get_text", lambda url, ua:
                        MERGER_6K if "A1" in url else "<div>Item 2.01 x</div><p>Big Filer, Inc. completed its acquisition of Y, Inc.</p>")
    data = resolver.fetch_ma_filings("1", "ua", start="2020-01-01", end="2026-12-31")
    assert {f["accession"] for f in data["filings"]} == {"R1", "A1"}


# ------------------------------------------------- extractor on the Einride case

EINRIDE_PASSAGE = (
    "On July 16, 2026, Einride AB (the “Company”) entered into an Agreement and Plan of Merger "
    "(the “Merger Agreement”) with Einride FUSE Merger Sub, Inc., a Delaware corporation and a wholly "
    "owned subsidiary of the Company (“Merger Sub”), Flipturn, Inc., a Delaware corporation "
    "(“Flipturn”), and Shareholder Representative Services LLC, solely in its capacity as the "
    "representative of the Flipturn stockholders. Pursuant to the Merger Agreement, Merger Sub will merge "
    "with and into Flipturn, with Flipturn surviving the merger and becoming a wholly owned subsidiary of the Company."
)


def test_extractor_recognizes_ab_registrant_and_emits_agreed_to_acquire():
    out = EdgarMAExtractor().parse_section(EINRIDE_PASSAGE, None)
    assert "Einride AB" in out["fused"]["orgs"]
    agreed = [e for e in out["raw_events"] if e["event_type"] == "AGREED_TO_ACQUIRE"]
    assert [(e["subject"], e["object"]) for e in agreed] == [("Einride AB", "Flipturn, Inc.")]


def test_reverse_triangular_merger_does_not_make_the_shell_the_counterparty():
    # The merger sub merging into Flipturn is the legal mechanism, not the
    # business relationship. The counterparty that matters to a pivot on
    # Einride AB is Flipturn, Inc.
    from providers.edgar_ma_provider import other_party
    out = EdgarMAExtractor().parse_section(EINRIDE_PASSAGE, None)
    agreed = next(e for e in out["raw_events"] if e["event_type"] == "AGREED_TO_ACQUIRE")
    assert other_party(agreed, "Einride") == "Flipturn, Inc."
