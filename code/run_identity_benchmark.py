#!/usr/bin/env python3
"""Run the identity candidate cohort without confusing evidence with ground truth."""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "code"))
from root_entity_resolver import resolve_company_root

VERIFIED = {"VERIFIED", "INDEPENDENTLY_VERIFIED"}
ABSTAIN = {"NO_MATCH", "REVIEW_REQUIRED"}


def evaluate(case, result):
    """Return a classification only when independently verified expectations suffice."""
    if case.get("verification_status") not in VERIFIED:
        return "NOT_SCORED"
    expected = case.get("expected") or {}
    status = expected.get("expected_resolution")
    lei = expected.get("target_lei")
    actual_status = result["status"]
    actual_lei = (result.get("root") or {}).get("lei")

    if status in ABSTAIN and not lei:
        return "CORRECT_ABSTENTION" if actual_status in ABSTAIN else "UNSUPPORTED_AUTO_RESOLUTION"
    if not lei:
        return "INSUFFICIENT_GROUND_TRUTH"
    if actual_status == "AUTO_RESOLVED":
        return "CORRECT_AUTO_RESOLUTION" if actual_lei == lei else "WRONG_AUTO_RESOLUTION"
    if actual_status in ABSTAIN:
        return "ABSTAINED_ON_VERIFIED_IDENTITY"
    return "UNEXPECTED_RESOLVER_STATUS"


def run(dataset, lei_db, rr_db):
    cases = dataset["cases"]
    rows = []
    for case in cases:
        name = case["input"]["company_name"]
        try:
            resolution = resolve_company_root(name, str(lei_db), str(rr_db)).to_dict()
            classification = evaluate(case, resolution)
            rows.append({
                "id": case["id"], "query": name,
                "verification_status": case.get("verification_status"),
                "expected": case.get("expected"),
                "classification": classification,
                "actual": resolution,
            })
        except Exception as exc:
            rows.append({
                "id": case["id"], "query": name,
                "verification_status": case.get("verification_status"),
                "classification": "EXECUTION_ERROR",
                "error": f"{type(exc).__name__}: {exc}",
            })
    counts = dict(sorted(Counter(row["classification"] for row in rows).items()))
    return {
        "schema": "corporate-helix/identity-benchmark-report/v1",
        "dataset_schema": dataset.get("schema"),
        "total_cases": len(rows),
        "scored_cases": sum(v for k, v in counts.items() if k not in
                            {"NOT_SCORED", "INSUFFICIENT_GROUND_TRUTH", "EXECUTION_ERROR"}),
        "classifications": counts,
        "results": rows,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path,
                        default=ROOT / "data/eval_study/identity_ground_truth_candidates_v1.json")
    parser.add_argument("--lei-db", type=Path, default=ROOT / "data/gleif_lei.sqlite")
    parser.add_argument("--rr-db", type=Path, default=ROOT / "data/gleif_rr.sqlite")
    parser.add_argument("--output", type=Path,
                        default=ROOT / "data/eval_study/identity_benchmark_results.json")
    args = parser.parse_args()
    for path in (args.dataset, args.lei_db, args.rr_db):
        if not path.is_file():
            parser.error(f"Missing required input: {path}")
    dataset = json.loads(args.dataset.read_text(encoding="utf-8"))
    report = run(dataset, args.lei_db, args.rr_db)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "results"}, indent=2))
    print(f"Report: {args.output}")
    if report["classifications"].get("WRONG_AUTO_RESOLUTION", 0) or report["classifications"].get("UNSUPPORTED_AUTO_RESOLUTION", 0):
        return 2
    return 1 if report["classifications"].get("EXECUTION_ERROR", 0) else 0


if __name__ == "__main__":
    raise SystemExit(main())
