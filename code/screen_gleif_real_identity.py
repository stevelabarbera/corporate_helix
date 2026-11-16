#!/usr/bin/env python3
"""Run real GLEIF identity screening against a migrated TEMPORARY L1 backup.

This is an observational screening, NOT an independently adjudicated accuracy
benchmark. Original L1 and L2 databases are not modified.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
from migrate_gleif_lookup_key import migrate
from root_entity_resolver import resolve_company_root

ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "data/eval_study/identity_ground_truth_candidates_v1.json"
EXTRA_NAMES = (
    "Sempra Energy", "Citrix Systems Inc", "Sony", "NTT",
    "Tenable Holdings, Inc.", "SentinelOne",
)


def screen(lei_path: Path, rr_path: Path, cohort_path: Path, output_path: Path, cohort_only: bool = False):
    dataset = json.loads(cohort_path.read_text(encoding="utf-8"))
    names = [c["input"]["company_name"] for c in dataset["cases"]]
    if not cohort_only:
        names.extend(EXTRA_NAMES)
    names = list(dict.fromkeys(names))

    if not lei_path.is_file() or not rr_path.is_file():
        raise FileNotFoundError("Both GLEIF L1 and L2 SQLite databases must exist")
    with sqlite3.connect(f"file:{rr_path.resolve().as_posix()}?mode=ro", uri=True) as rr:
        available = {row[1] for row in rr.execute("PRAGMA table_info(relationships)")}
        required = {"child_lei", "parent_lei", "relationship_type", "relationship_status"}
        if not required.issubset(available):
            raise RuntimeError(f"L2 relationships missing columns: {sorted(required - available)}")
        relationship_count = rr.execute("SELECT count(*) FROM relationships").fetchone()[0]

    with tempfile.TemporaryDirectory(prefix="helix-identity-screen-") as tmp:
        migrated = Path(tmp) / "gleif_lei.sqlite"
        with sqlite3.connect(f"file:{lei_path.resolve().as_posix()}?mode=ro", uri=True) as source:
            source_count = source.execute("SELECT count(*) FROM lei_entities").fetchone()[0]
            with sqlite3.connect(migrated) as dst:
                source.backup(dst)

        with sqlite3.connect(migrated) as dst:
            migrate(dst)
            migrated_count = dst.execute("SELECT count(*) FROM lei_entities").fetchone()[0]
            missing_keys = dst.execute(
                "SELECT count(*) FROM lei_entities WHERE legal_name_lookup_key IS NULL"
            ).fetchone()[0]

        if source_count != migrated_count or missing_keys:
            raise RuntimeError("L1 temporary migration consistency check failed")

        results = []
        for index, name in enumerate(names, 1):
            try:
                resolution = resolve_company_root(name, str(migrated), str(rr_path)).to_dict()
                root = resolution.get("root") or {}
                result = {
                    "company": name,
                    "status": resolution["status"],
                    "confidence": resolution["confidence"],
                    "root_name": root.get("legal_name"),
                    "root_lei": root.get("lei"),
                    "reason": resolution.get("reason"),
                    "seed_match_count": len(resolution.get("seed_matches") or []),
                    "candidate_count": len(resolution.get("candidates") or []),
                    "candidates": resolution.get("candidates"),
                    "seed_matches": resolution.get("seed_matches"),
                }
            except Exception as exc:
                result = {"company": name, "status": "EXECUTION_ERROR",
                          "error": f"{type(exc).__name__}: {exc}"}
            results.append(result)
            print(f"[{index:02d}/{len(names)}] {name}: {result['status']}"
                  f" | {result.get('root_name') or '-'}", flush=True)

    counts = dict(sorted(Counter(r["status"] for r in results).items()))
    report = {
        "schema": "corporate-helix/real-gleif-identity-screen/v1",
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "data_kind": "UNADJUDICATED_SCREEN_NOT_ACCURACY",
        "l1_source": str(lei_path.resolve()),
        "l2_source": str(rr_path.resolve()),
        "l1_rows": source_count,
        "l2_relationship_rows": relationship_count,
        "source_databases_modified": False,
        "cases": len(results),
        "statuses": counts,
        "verified_identity_accuracy": None,
        "results": results,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print("\nSUMMARY (not an accuracy score)")
    print(json.dumps({k: v for k, v in report.items() if k != "results"}, indent=2))
    print(f"Detailed report: {output_path}")
    return 1 if counts.get("EXECUTION_ERROR", 0) else 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lei-index", type=Path,
                        default=ROOT / "data/processed/gleif_lei.sqlite")
    parser.add_argument("--rr-index", type=Path,
                        default=ROOT / "data/processed/gleif_rr.sqlite")
    parser.add_argument("--cohort", type=Path, default=CASES)
    parser.add_argument("--output", type=Path,
                        default=ROOT / "data/eval_study/real_gleif_identity_screen.json")
    parser.add_argument("--cohort-only", action="store_true",
                        help="Screen only cohort entries; do not append short-name controls")
    args = parser.parse_args()
    return screen(args.lei_index, args.rr_index, args.cohort, args.output,
                  cohort_only=args.cohort_only)


if __name__ == "__main__":
    raise SystemExit(main())
