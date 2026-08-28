#!/usr/bin/env python3
"""
Regression test for the generalized (non-hardcoded) party extraction in
fetch_edgar_events.py. Runs entirely offline against real cached Broadcom/
VMware filing text in data/raw/edgar_broadcom_events.json — no network
needed, no company names hardcoded in the extraction logic under test.

This exists because fetch_edgar_events.py used to have Broadcom/VMware
literally hardcoded in infer_candidates(); the generalized replacement
uses defined-term extraction ('Full Name ("ShortName")') plus directional
action-phrase matching instead. This test locks in that the generalized
version reproduces (and in one case improves on) the original's behavior
on the real filings that motivated the benchmark in the first place.

Run: python3 code/test_event_extraction.py
"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from fetch_edgar_events import infer_candidates, norm_name

FIXTURE = Path(__file__).parent.parent / "data" / "raw" / "edgar_broadcom_events.json"
LUMEN_FIXTURE = Path(__file__).parent.parent / "data" / "raw" / "edgar_lumen_technologies_events.json"

EXPECTED = {
    ("2023-11-22", "2.01"): [("ACQUIRED", "HIGH")],
    ("2023-08-16", "1.01"): [("AGREED_TO_ACQUIRE", "MEDIUM")],  # corroborating financing filing, not a fresh agreement statement
    ("2022-05-26", "1.01"): [("AGREED_TO_ACQUIRE", "HIGH")],
    ("2022-04-18", "1.01"): [],  # non-M&A Item 1.01 (credit facility amendment, unrelated to VMware deal)
    ("2022-04-15", "1.01"): [],  # non-M&A Item 1.01
}


def word_boundary_match(query, title):
    """Mirrors find_cik()'s final fallback tier logic in fetch_edgar_events.py."""
    nq = norm_name(query)
    pat = re.compile(r"\b" + re.escape(nq) + r"\b")
    return bool(pat.search(norm_name(title)))


def run_cik_matching_regression():
    """
    Regression test for a real false positive found during manual testing:
    querying --company "Lumen" resolved to CIK 0001633978 (Lumentum Holdings
    Inc., an unrelated optical-components company) instead of Lumen
    Technologies, because plain substring matching found "lumen" inside
    "lumentum" — a character coincidence, not a real name relationship.
    Fixed by requiring word-boundary matches in the substring fallback tier.
    """
    cases = [
        ("Lumen", "Lumentum Holdings Inc.", False),
        ("Lumen", "Lumen Technologies, Inc.", True),
        ("Lumen", "CenturyLink, Inc.", False),
    ]
    failures = 0
    for query, title, expected in cases:
        got = word_boundary_match(query, title)
        if got != expected:
            failures += 1
            print(f"FAIL cik-match: find_cik({query!r}) vs title={title!r} -> matched={got}, expected {expected}")
        else:
            print(f"PASS cik-match: find_cik({query!r}) vs title={title!r} -> matched={got}")
    return failures


def tiered_resolve(query, companies):
    """
    Offline mirror of find_cik()'s tier 1-4 logic in fetch_edgar_events.py,
    minus the live SEC network call (same pattern as word_boundary_match()
    above). `companies` is a list of dicts with 'title', 'ticker', 'cik_str'
    keys, standing in for the real company_tickers.json payload.
    """
    q = query.strip()
    x = [e for e in companies if str(e.get("ticker", "")).casefold() == q.casefold()]
    if x:
        return x
    x = [e for e in companies if str(e.get("title", "")).strip().casefold() == q.casefold()]
    if x:
        return x
    nq = norm_name(q)
    x = [e for e in companies if norm_name(str(e.get("title", ""))) == nq]
    if x:
        return x
    if not nq:
        return []
    pat = re.compile(r"\b" + re.escape(nq) + r"\b")
    return [e for e in companies if pat.search(norm_name(str(e.get("title", ""))))]


def run_multi_match_regression():
    """
    Regression test for a gap found after the word-boundary fix landed: tier
    4 (word-boundary substring) can legitimately match MORE THAN ONE company
    when two titles share a standalone word (e.g. two different "Lumen ___"
    entities). fetch_edgar_events.py's CLI now refuses to proceed on an
    ambiguous match (raises SystemExit asking for --cik) instead of the old
    behavior of silently using matches[0] with a stderr-only warning -- that
    silent version was a real risk, since a wrong silent pick looked
    identical to "fewer real results" with no visible cause. This test
    locks in that the ambiguity is detected at the resolution-logic level;
    the loud-refusal itself lives in main() and needs a live network call
    to exercise end-to-end, so this covers detection, not full CLI behavior.
    """
    single = [
        {"title": "Lumen Technologies, Inc.", "ticker": "LUMN", "cik_str": 18926},
    ]
    ambiguous = [
        {"title": "Lumen Technologies, Inc.", "ticker": "LUMN", "cik_str": 18926},
        {"title": "Lumen Bioscience, Inc.", "ticker": "LMNB", "cik_str": 99999},
    ]

    failures = 0

    got = tiered_resolve("Lumen", single)
    if len(got) == 1 and got[0]["cik_str"] == 18926:
        print("PASS multi-match: single 'lumen'-titled company resolves unambiguously")
    else:
        failures += 1
        print(f"FAIL multi-match: expected exactly Lumen Technologies, got {got}")

    got = tiered_resolve("Lumen", ambiguous)
    if len(got) == 2:
        print("PASS multi-match: two 'lumen'-titled companies correctly surface as ambiguous "
              "(exercises the same tier-4 path the CLI silently resolves via matches[0])")
    else:
        failures += 1
        print(f"FAIL multi-match: expected 2 ambiguous matches, got {len(got)}: {got}")

    # Exact-title query should bypass tier-4 entirely and stay unambiguous
    # even when a same-word competitor exists in the pool.
    got = tiered_resolve("Lumen Technologies, Inc.", ambiguous)
    if len(got) == 1 and got[0]["cik_str"] == 18926:
        print("PASS multi-match: exact-title query stays unambiguous even with a same-word competitor present")
    else:
        failures += 1
        print(f"FAIL multi-match: exact-title query should have stayed unambiguous, got {got}")

    return failures


def run_divestiture_regression():
    """
    Regression test for the Lumen->Brightspeed / Lumen->Colt divestiture
    filings found during real testing. As of this test, buyer names are
    NOT auto-extracted for divestitures (see fetch_edgar_events.py comment
    on nested-appositive misattribution risk) — this test locks in that
    behavior: these filings should be flagged as likely divestitures with
    real candidate party names present, WITHOUT asserting a specific buyer.
    If a future change adds confident buyer extraction, update this test
    deliberately rather than letting it silently start asserting names.
    """
    if not LUMEN_FIXTURE.exists():
        print(f"SKIP: Lumen fixture not found at {LUMEN_FIXTURE}")
        return 0

    data = json.loads(LUMEN_FIXTURE.read_text(encoding="utf-8"))
    failures = 0
    checked = 0

    for filing in data["filings"]:
        if not filing["event_candidates"]:
            continue
        checked += 1
        sec = filing["sections"][0]
        events = infer_candidates(sec, filing["filing_date"], filing["accession"], filing["source_url"], "Lumen Technologies, Inc.")

        if len(events) != 1:
            failures += 1
            print(f"FAIL divestiture {filing['filing_date']}: expected 1 event, got {len(events)}")
            continue

        e = events[0]
        ok = (
            e["event_type"] == "M&A_CANDIDATE"
            and e["confidence"] == "REVIEW"
            and "DIVESTITURE" in (e["reason"] or "")
            and e["candidate_parties"]  # real names present, even if buyer role isn't asserted
            and e["acquirer"] is None  # must NOT assert a buyer given the known misattribution risk
        )
        if ok:
            print(f"PASS divestiture {filing['filing_date']}: flagged correctly, no buyer asserted, {len(e['candidate_parties'])} candidates present")
        else:
            failures += 1
            print(f"FAIL divestiture {filing['filing_date']}: {e}")

    return failures


def run():
    cik_failures = run_cik_matching_regression()
    print()
    multi_match_failures = run_multi_match_regression()
    print()
    divestiture_failures = run_divestiture_regression()
    print()

    if not FIXTURE.exists():
        print(f"SKIP: event-extraction fixture not found at {FIXTURE} (cik-matching tests above still ran).")
        return 1 if (cik_failures or multi_match_failures or divestiture_failures) else 0

    data = json.loads(FIXTURE.read_text(encoding="utf-8"))
    failures = 0
    checked = 0

    for filing in data["filings"]:
        for sec in filing["sections"]:
            key = (filing["filing_date"], sec["item"])
            events = infer_candidates(sec, filing["filing_date"], filing["accession"], filing["source_url"], "Broadcom Inc.")
            got = [(e["event_type"], e["confidence"]) for e in events if e["event_type"] != "M&A_CANDIDATE"]

            expected = EXPECTED.get(key)
            if expected is None:
                print(f"WARN: no expectation set for {key}, skipping")
                continue

            checked += 1
            if got != expected:
                failures += 1
                print(f"FAIL {key}: expected {expected}, got {got}")
                for e in events:
                    print(f"       -> {e['event_type']} conf={e['confidence']} acquirer={e['acquirer']!r} target={e['target']!r}")
            else:
                # Also sanity-check party direction on the ones that should resolve
                if events and events[0]["event_type"] != "M&A_CANDIDATE":
                    acq, tgt = events[0]["acquirer"], events[0]["target"]
                    if not (acq and "broadcom" in acq.lower() and tgt and "vmware" in tgt.lower()):
                        failures += 1
                        print(f"FAIL {key}: event type/confidence matched but party direction looks wrong: acquirer={acq!r} target={tgt!r}")
                        continue
                print(f"PASS {key}: {got}")

    total_failures = failures + cik_failures + multi_match_failures + divestiture_failures
    print(f"\n{checked - failures} event-extraction passed / {failures} failed; "
          f"3 cik-matching passed / {cik_failures} failed; "
          f"3 multi-match passed / {multi_match_failures} failed; "
          f"divestiture-flagging: {divestiture_failures} failed")
    return 1 if total_failures else 0


if __name__ == "__main__":
    sys.exit(run())
