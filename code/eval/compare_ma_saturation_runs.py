#!/usr/bin/env python3
"""Compare the immutable M&A-S1 results with a post-fix result directory."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVAL = ROOT / "code" / "eval"
if str(EVAL) not in sys.path:
    sys.path.insert(0, str(EVAL))

from run_ma_s1_baseline import load_json
from run_ma_s2_comparison import (
    BASELINE_RESULTS,
    S1_SNAPSHOT_REF,
    S2_RESULTS,
    compare_results,
    load_baseline,
)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--baseline-results", type=Path, default=BASELINE_RESULTS)
    ap.add_argument("--baseline-ref", default=S1_SNAPSHOT_REF)
    ap.add_argument("--results", type=Path, default=S2_RESULTS)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    comparisons = []
    for current_path in sorted(args.results.glob("*.json")):
        baseline_path = args.baseline_results / current_path.name
        try:
            baseline = load_baseline(current_path.stem, args.baseline_results, args.baseline_ref or None)
        except (FileNotFoundError, ValueError):
            continue
        comparisons.append(compare_results(baseline, load_json(current_path)))
    totals = {label: sum(item["counts"][label] for item in comparisons)
              for label in ("ADVANCED", "UNCHANGED", "REGRESSED", "ADDED", "REMOVED")}
    report = {"companies_compared": len(comparisons), "totals": totals, "companies": comparisons}
    if args.json:
        print(json.dumps(report, indent=2))
        return 0
    print(f"Companies compared: {len(comparisons)}")
    print(f"Advanced: {totals['ADVANCED']} | unchanged: {totals['UNCHANGED']} | regressed: {totals['REGRESSED']}")
    for item in comparisons:
        counts = item["counts"]
        print(f"  {item['company_id']}: +{counts['ADVANCED']} ={counts['UNCHANGED']} -{counts['REGRESSED']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
