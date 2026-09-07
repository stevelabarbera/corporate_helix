#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from expansion_bridges import (
    DomainCandidateExpansionProvider,
    GleifCompanyExpansionProvider,
    company_seed,
)
from iterative_expansion import run_expansion


def main() -> None:
    ap = argparse.ArgumentParser(description="Run the first live M4.3C company -> GLEIF iterative bridge.")
    ap.add_argument("--company", required=True)
    ap.add_argument("--lei", required=True, help="Explicit root LEI for this first vertical slice")
    ap.add_argument("--lei-index", default="data/processed/gleif_lei.sqlite")
    ap.add_argument("--rr-index", default="data/processed/gleif_rr.sqlite")
    ap.add_argument("--domain-candidates", help="Evaluated M4.3B domain-candidate JSON")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    seed = company_seed(args.company, args.lei)
    providers = [GleifCompanyExpansionProvider(args.lei_index, args.rr_index)]
    if args.domain_candidates:
        providers.append(DomainCandidateExpansionProvider.from_json(args.domain_candidates))
    result = run_expansion([seed], providers, max_iterations=5)

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
    domains = [f for f in result.facts if f.fact_type == "DOMAIN"]
    accepted_domains = [f for f in domains if f.status == "ACCEPTED"]
    review_domains = [f for f in domains if f.status == "REVIEW"]
    rejected_domains = [f for f in domains if f.status == "REJECTED"]

    print(f"Review corporate  : {len(review)}")
    print(f"Domains           : {len(domains)}")
    print(f"Accepted domains  : {len(accepted_domains)}")
    print(f"Review domains    : {len(review_domains)}")
    print(f"Rejected domains  : {len(rejected_domains)}")
    print()

    for fact in sorted(legal, key=lambda f: (f.value.casefold(), f.identifier or "")):
        print(f"[{fact.status}/{fact.confidence}] {fact.value}")
        print(f"  LEI             : {fact.identifier or '-'}")
        relationships = list(fact.metadata.get("relationships") or [])
        if not relationships:
            for ev in fact.evidence:
                for rel in ev.get("relationships") or []:
                    if rel and rel not in relationships:
                        relationships.append(rel)
        print(f"  Relationships   : {', '.join(relationships) or '-'}")
        print(f"  Corp confidence : {fact.metadata.get('corporate_confidence') or '-'}")
        print(f"  Infra confidence: {fact.metadata.get('infrastructure_attribution_confidence') or '-'}")

    if domains:
        print()
        print("DOMAIN FACTS")
        print("-" * 72)
        for fact in sorted(domains, key=lambda f: f.value.casefold()):
            print(f"[{fact.status}/{fact.confidence}] {fact.value}")
            print(f"  Entity          : {fact.metadata.get('entity_name') or '-'}")
            print(f"  Entity LEI      : {fact.metadata.get('entity_lei') or '-'}")
            print(f"  M4.3B decision  : {fact.metadata.get('m43b_disposition') or '-'}")
            print(f"  Infra confidence: {fact.metadata.get('infrastructure_attribution_confidence') or '-'}")


if __name__ == "__main__":
    main()
