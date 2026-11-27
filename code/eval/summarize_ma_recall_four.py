#!/usr/bin/env python3
"""Aggregate pinned four-company M&A-S1 results; do not infer all-deal recall.

This reads the existing run_ma_s1_baseline JSON files. It does not fetch SEC
data, alter any production parser, or treat missing results as zero deals.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

STAGES = (
    "cik_resolved", "filings_retrieved", "relevant_text_present",
    "locator_captured", "entity_recognized", "event_extracted",
    "candidate_emitted",
)


def load(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def summarize(study, results_dir):
    companies = []
    for spec in study["companies"]:
        path = Path(results_dir) / f'{spec["id"]}.json'
        if not path.exists():
            companies.append({
                "company": spec["company"], "id": spec["id"],
                "run_state": "NOT_RUN", "cik": spec.get("cik"),
                "expected_events": None, "candidate_emitted": None,
                "events": [],
            })
            continue
        result = load(path)
        expected = []
        for event in result.get("gold_events") or []:
            states = event.get("stages") or {}
            # This is the existing code's *strict event match*. Not identical
            # to finding a name mention or passing a candidate for review.
            candidate_emitted = states.get("candidate_emitted") is True
            event_extracted = states.get("event_extracted") is True
            # Counterparty candidate emission alone is *not* an M&A-event hit.
            # Monsanto/Bayer can emit a name while failing the gold transaction
            # type/status extraction. Require both before marking detected.
            discovered = candidate_emitted and event_extracted
            first_unpassed = next(
                (stage for stage in STAGES[1:] if states.get(stage) is not True),
                None,
            )
            expected.append({
                "id": event.get("id"),
                "counterparty": event.get("counterparty"),
                "expected_type": event.get("event_type"),
                "expected_status": event.get("status"),
                "found": discovered,
                "counterparty_candidate_emitted": candidate_emitted,
                "gold_event_extracted": event_extracted,
                "first_unpassed_stage": first_unpassed,
                "deepest_stage": event.get("deepest_stage"),
                "stage_flags": states,
            })
        companies.append({
            "id": spec["id"], "company": spec["company"],
            "run_state": "RAN",
            "cik": result.get("cik"),
            "expected_events": len(expected),
            "candidate_emitted": sum(bool(e["counterparty_candidate_emitted"]) for e in expected),
            "gold_events_extracted": sum(bool(e["gold_event_extracted"]) for e in expected),
            "fully_detected": sum(bool(e["found"]) for e in expected),
            "retrieval_filing_count": (result.get("retrieval") or {}).get("filing_count"),
            "retrieval_errors": (result.get("retrieval") or {}).get("errors") or [],
            "failure_classes": result.get("failure_classes") or [],
            "events": expected,
        })
    tested = [c for c in companies if c["run_state"] == "RAN"]
    num_events = sum(c["expected_events"] for c in tested)
    num_found = sum(c["fully_detected"] for c in tested)
    num_candidates = sum(c["candidate_emitted"] for c in tested)
    num_events_extracted = sum(c["gold_events_extracted"] for c in tested)
    retrieval_errors = sum(len(c["retrieval_errors"]) for c in tested)
    return {
        "study_id": study["study_id"],
        "companies_declared": len(study["companies"]),
        "companies_ran": len(tested),
        "known_sentinel_events_evaluated": num_events,
        "counterparty_candidate_emitted_for_sentinel_events": num_candidates,
        "gold_events_extracted_for_sentinel_events": num_events_extracted,
        "fully_detected_sentinel_events": num_found,
        "sentinel_event_detection_fraction": (
            round(num_found / num_events, 4)
            if num_events and len(tested) == len(study["companies"]) and not retrieval_errors
            else None
        ),
        "retrieval_error_count": retrieval_errors,
        "quality": "SENTINEL_ONLY_NOT_ALL_MA_RECALL",
        "companies": companies,
    }


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--study", default="data/eval_study/ma_recall_four_v1.json")
    p.add_argument("--results", default="data/eval_study/ma_recall_four_results")
    p.add_argument("--out", required=True)
    a = p.parse_args(argv)
    report = summarize(load(a.study), a.results)
    output = Path(a.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as out:
        json.dump(report, out, indent=2, ensure_ascii=False)
        out.write("\n")
    print(json.dumps({
        key: val for key, val in report.items() if key != "companies"
    }, indent=2))
    for c in report["companies"]:
        print(f'{c["id"]}: {c["run_state"]} | '
              f'events={c["expected_events"]} detected={c["fully_detected"]} '
              f'counterparty_candidates={c["candidate_emitted"]}')
        for e in c["events"]:
            print(f'  {e["counterparty"]}: '
                  f'{"FOUND" if e["found"] else "MISSED"} '
                  f'[{e["first_unpassed_stage"] or "full pipeline"}]')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
