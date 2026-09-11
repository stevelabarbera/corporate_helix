#!/usr/bin/env python3
"""
Corporation Helix -- recursive company M&A discovery.

Given a company, finds every merger/acquisition it has been part of via
SEC EDGAR 8-K filings, then recurses into every other company that
surfaces, until nothing new is found. When EDGAR has nothing left to say
about a company (most commonly: it stopped filing independently after
being absorbed), GLEIF's relationship data is consulted instead, since it
doesn't require independent SEC-filer status.

This wires EdgarMAExpansionProvider and GleifIdentityFallbackProvider into
the same run_expansion() engine already used for the GLEIF-only expansion
path (see run_iterative_company_domains.py) -- same architecture, EDGAR
data source, extended.

IMPORTANT: the default (live) fetch path requires network access to
sec.gov, which the environment this was built in does not have. Everything
in this file was verified offline against real downloaded EDGAR filing
data and a synthetic second hop (see tests/test_edgar_ma_provider.py) --
run a live smoke test against the real SEC API before trusting this in
production.

Usage:
    python3 run_company_ma_expansion.py --company "Cisco Systems, Inc." [--max-iterations 10] [--json]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from iterative_expansion import HelixFact, run_expansion
from providers.edgar_ma_provider import EdgarMAExpansionProvider
from providers.gleif_identity_fallback_provider import GleifIdentityFallbackProvider


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--company", required=True)
    ap.add_argument("--lei-index", default="data/processed/gleif_lei.sqlite")
    ap.add_argument("--rr-index", default="data/processed/gleif_rr.sqlite")
    ap.add_argument("--max-iterations", type=int, default=10)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    seed = HelixFact(
        fact_type="COMPANY", value=args.company, identifier=None,
        source="SEED", confidence="HIGH", status="ACCEPTED", pivot_eligible=True,
    )

    providers = [
        EdgarMAExpansionProvider(),
        GleifIdentityFallbackProvider(args.lei_index, args.rr_index),
    ]

    result = run_expansion([seed], providers, max_iterations=args.max_iterations)

    if args.json:
        print(json.dumps({
            "converged": result.converged,
            "stop_reason": result.stop_reason,
            "iterations_run": result.iterations_run,
            "entities": [
                {"name": f.value, "lei": f.identifier, "source": f.source,
                 "evidence_count": len(f.evidence)}
                for f in result.facts
            ],
        }, indent=2, ensure_ascii=False))
        return 0

    print("=" * 72)
    print("CORPORATION HELIX -- RECURSIVE M&A DISCOVERY")
    print("=" * 72)
    print(f"Seed        : {args.company}")
    print(f"Converged   : {result.converged}  ({result.stop_reason})")
    print(f"Iterations  : {result.iterations_run}")
    print(f"Entities    : {len(result.facts)}\n")

    for f in result.facts:
        marker = " (seed)" if f.source == "SEED" else f" (via {f.source})"
        lei = f" | LEI: {f.identifier}" if f.identifier else ""
        print(f"- {f.value}{marker}{lei}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
