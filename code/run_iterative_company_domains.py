#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from domain_discovery import _load_seeds
from expansion_bridges import (
    DiscoveringOfficialSiteDomainProvider,
    GleifCompanyExpansionProvider,
    SeededOfficialSiteDomainProvider,
    company_seed,
)
from iterative_expansion import run_expansion
from root_entity_resolver import resolve_company_root


def resolve_root_lei(company, explicit_lei, lei_index, rr_index):
    if explicit_lei:
        return explicit_lei, "OPERATOR"

    resolution = resolve_company_root(
        company=company,
        lei_db=lei_index,
        rr_db=rr_index,
    )

    if resolution.status != "AUTO_RESOLVED" or not resolution.root:
        print()
        print("=" * 72)
        print("CORPORATION HELIX — ROOT ENTITY RESOLUTION")
        print("=" * 72)
        print(f"Query      : {company}")
        print(f"Resolution : {resolution.status}")
        print(f"Confidence : {resolution.confidence}")
        print(f"Reason     : {resolution.reason}")

        if resolution.candidates:
            print()
            print("Top root candidates:")
            for i, candidate in enumerate(resolution.candidates[:10], 1):
                print(f"[{i}] {candidate.legal_name or candidate.lei}")
                print(f"    LEI      : {candidate.lei}")
                print(
                    f"    Coverage : {candidate.matched_seed_count}/"
                    f"{candidate.total_seed_count} ({candidate.coverage:.0%})"
                )
                print(f"    Score    : {candidate.score:.2f}")

        print()
        print("Root identity was not safe to select automatically.")
        print("Operator override:")
        print()
        print(
            '  python3 code/run_iterative_company_domains.py '
            f'--company "{company}" --lei <LEI>'
        )
        raise SystemExit(2)

    return resolution.root.lei, "M4.3D_ROOT_RESOLVER"


def main():
    ap = argparse.ArgumentParser(
        description=(
            "Run company -> root resolution -> GLEIF -> domain discovery -> "
            "deterministic attribution expansion."
        )
    )
    ap.add_argument("--company", required=True)
    ap.add_argument(
        "--lei",
        help="Explicit root LEI override. Omit for M4.3D automatic resolution.",
    )
    ap.add_argument(
        "--seeds",
        type=Path,
        help=(
            "Optional JSON URL seeds. Omit for zero-knowledge web discovery "
            "from trusted legal entities."
        ),
    )
    ap.add_argument("--max-results-per-entity", type=int, default=5)
    ap.add_argument("--lei-index", default="data/processed/gleif_lei.sqlite")
    ap.add_argument("--rr-index", default="data/processed/gleif_rr.sqlite")
    ap.add_argument("--timeout", type=int, default=20)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    root_lei, root_source = resolve_root_lei(
        args.company,
        args.lei,
        args.lei_index,
        args.rr_index,
    )

    seed = company_seed(args.company, root_lei, source=root_source)
    providers = [
        GleifCompanyExpansionProvider(args.lei_index, args.rr_index),
    ]

    if args.seeds:
        domain_seeds = _load_seeds(args.seeds)
        domain_provider = SeededOfficialSiteDomainProvider(
            domain_seeds,
            verify_official=True,
            timeout=args.timeout,
        )
        discovery_mode = "SEEDED"
    else:
        domain_provider = DiscoveringOfficialSiteDomainProvider(
            max_results_per_entity=args.max_results_per_entity,
            verify_official=True,
            timeout=args.timeout,
        )
        discovery_mode = "ZERO_KNOWLEDGE"

    providers.append(domain_provider)
    result = run_expansion([seed], providers, max_iterations=6)

    if args.json:
        payload = result.to_dict()
        payload["root_resolution"] = {
            "company": args.company,
            "lei": root_lei,
            "source": root_source,
        }
        payload["domain_discovery"] = {
            "mode": discovery_mode,
            "seed_file": str(args.seeds) if args.seeds else None,
            "max_results_per_entity": (
                args.max_results_per_entity if not args.seeds else None
            ),
            "search_errors": list(
                getattr(domain_provider, "search_errors", [])
            ),
        }
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return

    print("=" * 72)
    print("CORPORATION HELIX — ITERATIVE COMPANY / DOMAIN EXPANSION")
    print("=" * 72)
    print(f"Root query        : {args.company}")
    print(f"Root LEI          : {root_lei}")
    print(f"Root source       : {root_source}")
    print(f"Discovery mode    : {discovery_mode}")
    if args.seeds:
        print(f"Domain seed file  : {args.seeds}")
    else:
        print(f"Results / entity  : {args.max_results_per_entity}")
    print(f"Converged         : {result.converged}")
    print(f"Stop reason       : {result.stop_reason}")
    print(f"Iterations run    : {result.iterations_run}")
    print()

    for record in result.iterations:
        print(
            f"Iteration {record.iteration}: frontier={record.frontier_count} "
            f"discovered={record.discovered_count} new={record.new_fact_count} "
            f"new_pivots={record.new_pivot_count} "
            f"errors={len(record.provider_errors)}"
        )
        for error in record.provider_errors:
            print(
                f"  ERROR {error['provider']} on "
                f"{error['pivot_type']} {error['pivot_value']}: {error['error']}"
            )

    legal = [f for f in result.facts if f.fact_type == "LEGAL_ENTITY"]
    domains = [f for f in result.facts if f.fact_type == "DOMAIN"]
    accepted_domains = [
        f for f in domains
        if f.status == "ACCEPTED" and f.confidence == "HIGH"
    ]
    review_domains = [f for f in domains if f.status == "REVIEW"]
    rejected_domains = [f for f in domains if f.status == "REJECTED"]
    search_errors = list(getattr(domain_provider, "search_errors", []))

    print()
    print(f"Legal entities    : {len(legal)}")
    print(f"Domain facts      : {len(domains)}")
    print(f"Accepted domains  : {len(accepted_domains)}")
    print(f"Review domains    : {len(review_domains)}")
    print(f"Rejected domains  : {len(rejected_domains)}")
    print(f"Search errors     : {len(search_errors)}")
    print()

    for fact in sorted(
        domains,
        key=lambda f: (f.value.casefold(), f.subject or ""),
    ):
        print(f"[{fact.status}/{fact.confidence}] {fact.value}")
        print(f"  Entity          : {fact.subject or '-'}")
        print(f"  LEI             : {fact.identifier or '-'}")
        print(
            f"  Disposition     : "
            f"{fact.metadata.get('domain_disposition') or '-'}"
        )
        print(f"  Pivot eligible  : {fact.can_pivot()}")
        evidence_types = sorted({
            str(
                e.get("evidence_type")
                or e.get("type")
                or "UNKNOWN"
            )
            for e in fact.evidence
        })
        print(f"  Evidence types  : {', '.join(evidence_types)}")

    if search_errors:
        print()
        print("SEARCH ERRORS")
        print("-" * 72)
        for error in search_errors:
            print(
                f"{error.get('entity_name') or error.get('entity_lei')}: "
                f"{error.get('error')}"
            )


if __name__ == "__main__":
    main()
