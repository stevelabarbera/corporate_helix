#!/usr/bin/env python3
"""Coverage manifest (docs/BACKLOG.md "Foundation"): metadata-only accounting of
what the EDGAR retrieval layer does with every filing, and why."""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))

import providers.edgar_resolver as resolver
from providers import edgar_coverage as cov


def _subs(rows, name="Example AB"):
    """rows: (form, date, items)"""
    return {"name": name, "cik": "0000000001", "filings": {"recent": {
        "form": [r[0] for r in rows], "filingDate": [r[1] for r in rows],
        "items": [r[2] for r in rows],
        "accessionNumber": [f"0000000001-26-{i:06d}" for i in range(len(rows))],
        "primaryDocument": [f"doc{i}.htm" for i in range(len(rows))],
    }}}


EINRIDE_LIKE = [
    ("6-K", "2026-07-21", ""), ("6-K", "2026-06-01", ""), ("20-F", "2026-03-20", ""),
    ("F-4", "2026-02-01", ""), ("425", "2026-02-02", ""), ("EFFECT", "2026-02-10", ""),
    ("6-K", "2019-01-01", ""),
]


def test_classification_of_each_family():
    d = cov.classify_filing
    assert d("8-K", "2.01,9.01")[0] == cov.FETCHED_ITEM_GATED
    assert d("8-K/A", "1.01")[0] == cov.FETCHED_ITEM_GATED
    assert d("8-K", "5.02")[0] == cov.SKIP_ITEM_GATE
    assert d("8-K", "")[0] == cov.SKIP_NO_ITEMS
    for f in ("10-K", "20-F", "40-F", "6-K", "6-K/A"):
        assert d(f, "")[0] == cov.FETCHED_LOCATOR
    assert d("F-4", "")[0] == cov.SKIP_UNSUPPORTED_DEAL
    assert d("10-Q", "")[0] == cov.SKIP_UNSUPPORTED_DEAL
    assert d("EFFECT", "")[0] == cov.SKIP_UNSUPPORTED_OTHER


def test_manifest_accounts_for_every_filing_and_window():
    m = cov.build_manifest(_subs(EINRIDE_LIKE), start="2025-01-01", end="2026-12-31")
    assert m["totals"] == {"filings_total": 7, "in_window": 6, "retrievable": 3}
    assert len(m["rows"]) == 7                                  # nothing is dropped from the ledger
    assert m["rows"][-1]["disposition"] == cov.OUT_OF_WINDOW
    assert m["by_disposition"][cov.FETCHED_LOCATOR] == 3


def test_flags_name_the_unretrieved_deal_forms():
    m = cov.build_manifest(_subs(EINRIDE_LIKE), start="2025-01-01", end="2026-12-31")
    joined = " ".join(m["flags"])
    assert "F-4 x1" in joined and "425 x1" in joined
    assert "NOTHING RETRIEVED" not in joined


def test_nothing_retrieved_flag_is_the_pre_fix_einride_signature():
    # A filer whose forms are all outside the retrieval set looked exactly
    # like this before ADR-EDGAR-012: lots of filings, zero eligible.
    m = cov.build_manifest(_subs([("F-4", "2026-02-01", ""), ("EFFECT", "2026-02-02", "")]),
                           start="2025-01-01", end="2026-12-31")
    assert any(f.startswith("NOTHING RETRIEVED") for f in m["flags"])


def test_8k_without_item_metadata_is_flagged_not_hidden():
    m = cov.build_manifest(_subs([("8-K", "2026-01-01", ""), ("8-K", "2026-01-02", "2.01")]),
                           start="2025-01-01", end="2026-12-31")
    assert m["by_disposition"][cov.SKIP_NO_ITEMS] == 1
    assert any("no item metadata" in f for f in m["flags"])


def test_pages_overlapping_window_are_reported():
    raw = _subs([("8-K", "2026-01-01", "2.01")])
    raw["filings"]["files"] = [
        {"name": "a.json", "filingFrom": "2020-01-01", "filingTo": "2025-12-31"},
        {"name": "b.json", "filingFrom": "1994-01-01", "filingTo": "2019-12-31"},
    ]
    pages = cov.summarize_pages(raw, start="2024-01-01", end="2026-12-31")
    assert [p["overlaps_window"] for p in pages] == [True, False]
    m = cov.build_manifest(raw, start="2024-01-01", end="2026-12-31", pages=pages)
    assert any("older submissions page" in f for f in m["flags"])


def test_manifest_matches_what_the_collectors_actually_fetch(monkeypatch):
    """Parity: the manifest must never claim a filing is retrievable that the
    real collectors skip (or vice versa). Guards drift between the two."""
    rows = EINRIDE_LIKE + [("8-K", "2026-03-01", "2.01"), ("8-K", "2026-03-02", "5.02"),
                           ("8-K", "2026-03-03", ""), ("10-K", "2026-02-15", ""), ("10-Q", "2026-05-01", "")]
    subs = _subs(rows)
    monkeypatch.setattr(resolver, "_get_json", lambda url, ua: subs)
    # every document "contains" an M&A signal so the locator/section gates pass
    monkeypatch.setattr(resolver, "_get_text", lambda url, ua:
                        "<div>Item 2.01 Completion of Acquisition</div><p>Example completed its acquisition of Target, Inc.</p>")
    data = resolver.fetch_ma_filings("1", "t@example.com", start="2025-01-01", end="2026-12-31")
    fetched_by_collectors = {f["accession"] for f in data["filings"]}

    m = cov.build_manifest(subs, start="2025-01-01", end="2026-12-31")
    eligible = {r["accession"] for r in m["rows"] if r["disposition"] in cov.FETCHED}
    assert eligible == fetched_by_collectors


def test_cli_offline_writes_json_and_markdown(tmp_path, capsys):
    from eval.coverage_manifest import main
    p = tmp_path / "subs.json"
    p.write_text(json.dumps(_subs(EINRIDE_LIKE, name="Einride AB")), encoding="utf-8")
    out = tmp_path / "out"
    assert main(["--submissions-json", str(p), "--out-dir", str(out), "--start", "2025-01-01"]) == 0
    assert (out / "cik0000000001.json").exists()
    md = (out / "cik0000000001.md").read_text(encoding="utf-8")
    assert "Einride AB" in md and "F-4 x1" in md
