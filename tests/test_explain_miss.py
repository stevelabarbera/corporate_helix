#!/usr/bin/env python3
"""explain_miss: shows the sentences and the reason behind a miss, using the same parse path as the baseline harness."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))

from eval import explain_miss as em
from eval import run_ma_s1_baseline as h
from parsers.edgar_longform_locator import locate_ma_regions
from providers.edgar_ma_provider import EdgarMAExpansionProvider

PROVIDER = EdgarMAExpansionProvider(fetch_filings_fn=lambda _: {})


def _filing(text, form="10-K"):
    return {"accession": "0000000001-26-000001", "form": form, "filing_date": "2026-03-01",
            "raw_text": text, "sections": locate_ma_regions(text, form=form)}


def _verdicts(gold, text, form="10-K"):
    rows = em.explain(gold, [_filing(text, form)], extractor=PROVIDER.extractor, provider=PROVIDER)
    return [r["verdict"] for r in rows], rows


def test_find_passages_merges_adjacent_hits_and_adds_context():
    text = "Intro sentence. We bought Acme Widgets. Acme grew fast. Unrelated tail. Another tail. End."
    out = em.find_passages(text, ["Acme"], context=1)
    assert len(out) == 1 and "Intro sentence." in out[0] and "Unrelated tail." in out[0]


def test_found_when_event_matches_gold():
    gold = {"counterparty": "Humio Limited", "event_type": "ACQUIRED", "status": "COMPLETED"}
    v, _ = _verdicts(gold, "In March 2021, we acquired Humio Limited (\u201cHumio\u201d), a Danish company, for cash. "
                           "The purchase price allocation is described below.")
    assert v == ["FOUND"]


def test_completed_the_acquisition_of_is_now_covered_by_the_narrative_grammar():
    # Was EVENT_GRAMMAR_MISS before REGISTRANT_ACQUISITION_NARRATIVE (2026-10-15).
    gold = {"counterparty": "Target Software, Inc.", "event_type": "ACQUIRED", "status": "COMPLETED"}
    v, _ = _verdicts(gold, "In March 2024, we completed the acquisition of Target Software, Inc. (\u201cTarget\u201d) for cash. "
                           "The purchase price allocation is described below.")
    assert v == ["FOUND"]


def test_event_type_mismatch_is_reported_when_gold_type_differs():
    # My own CrowdStrike gold labelled tuck-ins AGREED_TO_ACQUIRE; a 10-K says "completed".
    gold = {"counterparty": "Humio Limited", "event_type": "AGREED_TO_ACQUIRE", "status": "COMPLETED"}
    v, rows = _verdicts(gold, "In March 2021, we acquired Humio Limited (\u201cHumio\u201d), a Danish company, for cash. "
                              "The purchase price allocation is described below.")
    assert v == ["EVENT_TYPE_MISMATCH"]
    assert "ACQUIRED" in rows[0]["why"]


def test_suffixless_name_reports_which_backend_saw_it_and_the_weights():
    gold = {"counterparty": "SGNL", "event_type": "ACQUIRED", "status": "COMPLETED"}
    v, rows = _verdicts(gold, "In January 2026, we completed the acquisition of SGNL, a leading identity "
                              "security company, for approximately $740 million.")
    assert v[0] in {"ENTITY_BELOW_THRESHOLD", "ENTITY_NOT_SEEN", "EVENT_GRAMMAR_MISS", "FOUND"}
    # Whatever the verdict, the per-backend evidence must be present so the cause is inspectable.
    assert set(rows[0]["backends"]) == {b.name for b in PROVIDER.extractor.backends}
    assert all("weight" in b for b in rows[0]["backends"].values())


def test_not_in_region_when_locator_skips_the_passage():
    gold = {"counterparty": "Zeta Corp", "event_type": "ACQUIRED", "status": "COMPLETED"}
    filing = _filing("Zeta Corp is a customer of ours.")          # no M&A keywords -> no region
    rows = em.explain(gold, [filing], extractor=PROVIDER.extractor, provider=PROVIDER)
    assert [r["verdict"] for r in rows] == ["NOT_IN_REGION"]


def test_cache_avoids_a_second_download(tmp_path):
    calls = []
    fetch = em.cached_get_text(tmp_path, lambda url, ua: (calls.append(url) or "body"))
    assert fetch("http://x/a", "ua") == "body" and fetch("http://x/a", "ua") == "body"
    assert calls == ["http://x/a"]


def test_cli_text_file_mode_writes_a_report(tmp_path, capsys):
    f = tmp_path / "doc.txt"
    f.write_text("In 2025 we completed the acquisition of Target Software, Inc. for cash.")
    out = tmp_path / "out"
    assert em.main(["--text-file", str(f), "--names", "Target Software", "--out-dir", str(out)]) == 0
    assert (out / "target_software.md").exists()
    assert "Miss explanation" in capsys.readouterr().out


def test_audit_corpus_unwraps_fpi_forms_like_production():
    wrapped = ("<p>On July 16, 2026, Example AB (the “Company”) entered\ninto an Agreement and Plan "
               "of Merger with Target Software, Inc.</p>")
    subs = {"name": "Example AB", "filings": {"recent": {
        "form": ["6-K"], "filingDate": ["2026-07-21"], "items": [""],
        "accessionNumber": ["A1"], "primaryDocument": ["a.htm"]}}}
    _, filings, _ = h.collect_audit_filings(
        "1", "ua", start="2026-01-01", end="2026-12-31",
        load_submissions_fn=lambda cik, ua: ("0000000001", subs), get_text_fn=lambda u, ua: wrapped)
    assert "entered into an Agreement" in filings[0]["raw_text"]


def test_even_a_plain_suffixed_name_can_lose_its_vote_to_spelling_variants():
    # Finding from building this tool: with no "(the "X")" alias definition,
    # regex sees "Target Software, Inc." (0.5) and spaCy sees "Target Software"
    # (1.0). Pooled they would clear the 1.5 threshold; counted per spelling,
    # neither does, and the organization is dropped.
    gold = {"counterparty": "Target Software, Inc.", "event_type": "ACQUIRED", "status": "COMPLETED"}
    v, rows = _verdicts(gold, "In March 2024, we completed the acquisition of Target Software, Inc. for cash. "
                              "The purchase price allocation is described below.")
    assert v == ["ENTITY_SPLIT_VOTE"]
    assert rows[0]["backends"]["regex"]["orgs_matching_name"] == ["Target Software, Inc."]
    assert rows[0]["backends"]["spacy"]["orgs_matching_name"] == ["Target Software"]


def test_short_gold_name_vs_full_legal_name_is_flagged_not_called_below_threshold():
    # Real CrowdStrike 10-K: backends agree on "SGNL.AI, Inc." (1.5 >= threshold), gold says "SGNL".
    gold = {"counterparty": "SGNL", "event_type": "AGREED_TO_ACQUIRE", "status": "COMPLETED"}
    text = ("On January 7, 2026, the Company entered into a definitive agreement to acquire 100 % of the equity "
            "interest of SGNL.AI, Inc., a leader in continuous identity. The acquisition closed on February 20, 2026.")
    v, rows = _verdicts(gold, text)
    assert v == ["EVENT_GRAMMAR_MISS"]
    assert "NAME FORM" in rows[0]["why"]
