#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from expansion_bridges import GleifCompanyExpansionProvider, company_seed
from iterative_expansion import run_expansion


def main() -> None:
    ap = argparse.ArgumentParser(description="Run the first live M4.3C company -> GLEIF iterative bridge.")
    ap.add_argument("--company", required=True)
    ap.add_argument("--lei", required=True, help="Explicit root LEI for this first vertical slice")
    ap.add_argument("--lei-index", default="data/processed/gleif_lei.sqlite")
    ap.add_argument("--rr-index", default="data/processed/gleif_rr.sqlite")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    seed = company_seed(args.company, args.lei)
    provider = GleifCompanyExpansionProvider(args.lei_index, args.rr_index)
    result = run_expansion([seed], [provider], max_iterations=5)

    if args.json:
        print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
        return

    print("=" * 72)
    print("CORPORATION HELIX — M4.3C ITERATIVE COMPANY EXPANSION")
    print("=" * 72)
    print(f"Root              : {args.company}")
    print(f"Root LEI          : {args.lei}")
    print(f"Converged         : {result.converged}")
    print(f"Stop reason       : {result.stop_reason}")
    print(f"Iterations run    : {result.iterations_run}")
    print()

    for record in result.iterations:
        print(
            f"Iteration {record.iteration}: frontier={record.frontier_count} "
            f"discovered={record.discovered_count} new={record.new_fact_count} "
            f"new_pivots={record.new_pivot_count} errors={len(record.provider_errors)}"
        )

    legal = [f for f in result.facts if f.fact_type == "LEGAL_ENTITY"]
    accepted = [f for f in legal if f.status == "ACCEPTED"]
    review = [f for f in legal if f.status == "REVIEW"]

    print()
    print(f"Legal entities    : {len(legal)}")
    print(f"Accepted corporate: {len(accepted)}")
    print(f"Review corporate  : {len(review)}")
    print()

    for fact in sorted(legal, key=lambda f: (f.value.casefold(), f.identifier or "")):
        print(f"[{fact.status}/{fact.confidence}] {fact.value}")
        print(f"  LEI             : {fact.identifier or '-'}")
        print(f"  Relationships   : {', '.join(fact.metadata.get('relationships') or []) or '-'}")
        print(f"  Corp confidence : {fact.metadata.get('corporate_confidence') or '-'}")
        print(f"  Infra confidence: {fact.metadata.get('infrastructure_attribution_confidence') or '-'}")


if __name__ == "__main__":
    main()
