#!/usr/bin/env python3
"""Reproducible GLEIF identity-start screening; not a ground-truth accuracy score.

Run:
 python3 code/run_identity_start_benchmark.py --cohort corporate_helix_start_cohort_v1.csv \
   --lei-index data/processed/gleif_lei.sqlite --rr-index data/processed/gleif_rr.sqlite \
   --output data/eval_study/identity_start_v1.json

The cohort must be frozen before running. No automatic match is counted as
verified without independent adjudication.
"""
import argparse
import csv
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from root_entity_resolver import resolve_company_root


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--cohort", required=True)
    p.add_argument("--lei-index", default="data/processed/gleif_lei.sqlite")
    p.add_argument("--rr-index", default="data/processed/gleif_rr.sqlite")
    p.add_argument("--output", required=True)
    args = p.parse_args()
    with open(args.cohort, newline="", encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    names = [r["company_name"].strip() for r in rows]
    if len(names) != 100 or len(set(n.casefold() for n in names)) != 100:
        p.error("Expected exactly 100 distinct company names in the frozen cohort")
    results = []
    for i, name in enumerate(names, 1):
        try:
            resolution = resolve_company_root(
                name, args.lei_index, args.rr_index
            )
            item = {
                "company_name": name,
                "status": resolution.status,
                "confidence": resolution.confidence,
                "reason": resolution.reason,
                "proposed_root": resolution.root.to_dict() if resolution.root else None,
                "candidate_count": len(resolution.candidates),
                "candidates": [c.to_dict() for c in resolution.candidates],
                "seed_match_count": len(resolution.seed_matches),
                "ground_truth_status": "NOT_ADJUDICATED",
            }
        except Exception as exc:
            item = {
                "company_name": name,
                "status": "ERROR",
                "error": f"{type(exc).__name__}: {exc}",
                "ground_truth_status": "NOT_ADJUDICATED",
            }
        results.append(item)
        print(f"[{i:03d}/100] {name}: {item['status']}", file=sys.stderr)
    counts = Counter(x["status"] for x in results)
    report = {
        "schema": "corporate-helix/identity-start-screen/v1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "cohort_file": str(Path(args.cohort).resolve()),
        "cohort_size": len(results),
        "status_counts": dict(sorted(counts.items())),
        "verified_successes": None,
        "false_positive_auto_resolutions": None,
        "notes": [
            "This is a GLEIF root-resolution screen, not full EDGAR/M&A recall.",
            "AUTO_RESOLVED means the resolver proposed an identity, not independent verification.",
            "REVIEW_REQUIRED candidates must not be used as trusted graph pivots.",
            "Errors are counted separately from no-match outcomes.",
        ],
        "results": results,
    }
    target = Path(args.output)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"output": str(target), "status_counts": report["status_counts"],
                      "verified_successes": None}, indent=2))
    return 1 if counts.get("ERROR", 0) else 0


if __name__ == "__main__":
    raise SystemExit(main())
