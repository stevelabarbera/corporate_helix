#!/usr/bin/env python3
"""Capture and compare a post-baseline M&A run without altering M&A-S1.

M&A-S1 is the frozen control.  This runner writes a second result tree and
reports event-by-event movement against the control so parser improvements can
be measured without destroying the evidence that motivated them.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
EVAL = ROOT / "code" / "eval"
if str(EVAL) not in sys.path:
    sys.path.insert(0, str(EVAL))

from run_ma_s1_baseline import company_spec, load_json, run_baseline

BASELINE_RESULTS = ROOT / "data/eval_study/ma_saturation_results"
S2_RESULTS = ROOT / "data/eval_study/ma_saturation_results_s2"
# Final commit containing all 12 results before post-baseline fixes were
# verified and selected result files were refreshed in place.
S1_SNAPSHOT_REF = "6211068"

STAGE_ORDER = (
    "CIK_UNRESOLVED",
    "CIK_RESOLVED",
    "FILINGS_RETRIEVED",
    "RELEVANT_TEXT_PRESENT",
    "LOCATOR_CAPTURED",
    "ENTITY_RECOGNIZED",
    "EVENT_EXTRACTED",
    "CANDIDATE_EMITTED",
)
STAGE_RANK = {stage: rank for rank, stage in enumerate(STAGE_ORDER)}


def load_result_at_ref(ref: str, path: Path) -> dict[str, Any]:
    """Read a frozen result from Git rather than trusting the working tree."""
    try:
        relative = path.resolve().relative_to(ROOT.resolve())
    except ValueError as exc:
        raise ValueError(f"Baseline path must be inside the repository: {path}") from exc
    try:
        rendered = subprocess.check_output(
            ["git", "show", f"{ref}:{relative.as_posix()}"],
            cwd=ROOT, text=True, stderr=subprocess.PIPE,
        )
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or "").strip()
        raise FileNotFoundError(f"Frozen baseline not found at {ref}:{relative}: {detail}") from exc
    return json.loads(rendered)


def load_baseline(company_id: str, baseline_results: Path, baseline_ref: str | None) -> dict[str, Any]:
    path = baseline_results / f"{company_id}.json"
    return load_result_at_ref(baseline_ref, path) if baseline_ref else load_json(path)


def compare_results(baseline: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
    """Compare matching gold-event IDs and retain additions/removals honestly."""
    before = {event["id"]: event for event in baseline.get("gold_events", [])}
    after = {event["id"]: event for event in current.get("gold_events", [])}
    rows = []
    for event_id in sorted(before.keys() | after.keys()):
        old = before.get(event_id)
        new = after.get(event_id)
        if old is None:
            movement = "ADDED"
        elif new is None:
            movement = "REMOVED"
        else:
            old_rank = STAGE_RANK.get(old.get("deepest_stage"), -1)
            new_rank = STAGE_RANK.get(new.get("deepest_stage"), -1)
            movement = "ADVANCED" if new_rank > old_rank else "REGRESSED" if new_rank < old_rank else "UNCHANGED"
        rows.append({
            "event_id": event_id,
            "counterparty": (new or old or {}).get("counterparty"),
            "baseline_stage": old.get("deepest_stage") if old else None,
            "current_stage": new.get("deepest_stage") if new else None,
            "movement": movement,
        })
    counts = {label: sum(row["movement"] == label for row in rows)
              for label in ("ADVANCED", "UNCHANGED", "REGRESSED", "ADDED", "REMOVED")}
    return {
        "company_id": current.get("company_id") or baseline.get("company_id"),
        "baseline_commit": baseline.get("baseline_commit"),
        "current_commit": current.get("baseline_commit"),
        "counts": counts,
        "events": rows,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--company", required=True, help="Study company id, e.g. tenable")
    ap.add_argument("--study", type=Path, default=ROOT / "data/eval_study/ma_saturation_pilot_v1.json")
    ap.add_argument("--gold-dir", type=Path, default=ROOT / "data/eval_gold")
    ap.add_argument("--baseline-results", type=Path, default=BASELINE_RESULTS)
    ap.add_argument(
        "--baseline-ref", default=S1_SNAPSHOT_REF,
        help="Git ref containing the frozen S1 snapshot; pass an empty value to read baseline-results from disk",
    )
    ap.add_argument("--results", type=Path, default=S2_RESULTS)
    ap.add_argument("--start", default="2015-01-01")
    ap.add_argument("--end", default="2026-12-31")
    ap.add_argument("--user-agent", default="CorporationHelix research contact@example.com")
    ap.add_argument("--overwrite", action="store_true", help="Replace an existing S2 result for this company")
    args = ap.parse_args()

    baseline_path = args.baseline_results / f"{args.company}.json"
    try:
        baseline = load_baseline(args.company, args.baseline_results, args.baseline_ref or None)
    except (FileNotFoundError, ValueError) as exc:
        raise SystemExit(str(exc)) from exc
    output = args.results / f"{args.company}.json"
    if output.exists() and not args.overwrite:
        raise SystemExit(f"Post-fix result already exists: {output}\nUse --overwrite only for an intentional replacement.")

    study = load_json(args.study)
    spec = company_spec(study, args.company)
    gold_path = args.gold_dir / f"{args.company}.json"
    if not gold_path.exists():
        raise SystemExit(f"Gold file not found: {gold_path}")
    result = run_baseline(
        spec, load_json(gold_path), user_agent=args.user_agent,
        start=args.start, end=args.end,
    )
    result["measurement_phase"] = "M&A-S2_POST_FIX"
    baseline_label = str(baseline_path.relative_to(ROOT))
    if args.baseline_ref:
        baseline_label = f"git:{args.baseline_ref}:{baseline_label}"
    result["comparison_baseline"] = baseline_label
    result["notes"] = (
        "Post-fix measurement run; compared with the immutable M&A-S1 control. "
        "Production behavior was measured as found at current_commit."
    )

    comparison = compare_results(baseline, result)
    args.results.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n")
    print(f"Wrote {output.relative_to(ROOT)}")
    print(f"Compared with {baseline_label}")
    for row in comparison["events"]:
        print(f"  {row['event_id']}: {row['baseline_stage']} -> {row['current_stage']} [{row['movement']}]")
    counts = comparison["counts"]
    print(f"Advanced: {counts['ADVANCED']} | unchanged: {counts['UNCHANGED']} | regressed: {counts['REGRESSED']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
