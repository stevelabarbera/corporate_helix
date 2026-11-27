#!/usr/bin/env python3
"""Corporate Helix: SEC M&A candidates + GLEIF L2 relationship evidence.

The graph preserves independent SEC event and GLEIF accounting relationship
evidence. Neither parser candidates nor L2 edges authorize recursion or ASM
attribution by themselves. --json includes full facts and source coverage.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from iterative_expansion import HelixFact
from providers.edgar_ma_provider import EdgarMAExpansionProvider
from providers.gleif_relationship_provider import GleifRelationshipEvidenceProvider
from ma_cross_source import run_integrated


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--company", required=True)
    ap.add_argument("--lei-index", default="data/processed/gleif_lei.sqlite")
    ap.add_argument("--rr-index", default="data/processed/gleif_rr.sqlite")
    ap.add_argument("--max-iterations", type=int, default=10)
    ap.add_argument("--max-gleif-edges", type=int, default=150)
    ap.add_argument("--max-sec-candidates", type=int, default=100)
    ap.add_argument("--as-of", default=None,
                    help="GLEIF snapshot eligibility date YYYY-MM-DD")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    seed = HelixFact(
        fact_type="COMPANY", value=args.company, identifier=None,
        source="SEED", confidence="HIGH", status="ACCEPTED",
        pivot_eligible=True,
    )
    edgar = EdgarMAExpansionProvider()
    gleif = GleifRelationshipEvidenceProvider(
        args.lei_index, args.rr_index, as_of_date=args.as_of,
        max_edges=args.max_gleif_edges,
    )
    result, integration = run_integrated(
        seed, edgar, gleif, max_iterations=args.max_iterations,
        max_sec_candidates=args.max_sec_candidates,
    )

    if args.json:
        print(json.dumps({
            **result.to_dict(),
            "cross_source": integration,
        }, indent=2, ensure_ascii=False))
        return 0

    print("=" * 72)
    print("CORPORATE HELIX -- SEC AND GLEIF RELATIONSHIP DISCOVERY")
    print("=" * 72)
    print(f"Seed        : {args.company}")
    print(f"Converged   : {result.converged} ({result.stop_reason})")
    print(f"Iterations  : {result.iterations_run}")
    print(f"Facts       : {len(result.facts)}")
    print(f"GLEIF edges : {integration['relationship_facts']}")
    print(f"SEC links   : {len(integration['links'])}")
    print()
    for fact in result.facts:
        if fact.fact_type == "CORPORATE_RELATIONSHIP":
            child, parent = fact.metadata["child"], fact.metadata["parent"]
            print(f"- {child.get('legal_name') or child['lei']} "
                  f"--{fact.metadata['relationship_type']}--> "
                  f"{parent.get('legal_name') or parent['lei']} "
                  "(GLEIF L2, REVIEW)")
        else:
            print(f"- {fact.value} ({fact.source}, {fact.status})")
    if integration["errors"]:
        print(f"GLEIF enrichment errors: {len(integration['errors'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
