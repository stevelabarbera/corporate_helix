#!/usr/bin/env python3
"""Corporate Helix: SEC M&A candidates + GLEIF L2 relationship evidence.

The graph preserves independent SEC event and GLEIF accounting relationship
evidence. Neither parser candidates nor L2 edges authorize recursion or ASM
attribution by themselves. --json includes full facts and source coverage.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from iterative_expansion import HelixFact
from providers.edgar_ma_provider import EdgarMAExpansionProvider
from providers.gleif_relationship_provider import GleifRelationshipEvidenceProvider
from ma_cross_source import run_integrated
from ma_bidirectional import investigate_l2_leads
from providers.edgar_resolver import fetch_ma_filings, resolve_cik_by_name


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--company", required=True)
    ap.add_argument("--cik", default=None, help="SEC CIK for delisted issuers")
    ap.add_argument("--sec-user-agent", default=os.environ.get("SEC_USER_AGENT"))
    ap.add_argument("--lei-index", default="data/processed/gleif_lei.sqlite")
    ap.add_argument("--rr-index", default="data/processed/gleif_rr.sqlite")
    ap.add_argument("--max-iterations", type=int, default=10)
    ap.add_argument("--max-gleif-edges", type=int, default=150)
    ap.add_argument("--max-sec-candidates", type=int, default=100)
    ap.add_argument("--gleif-sec-probes", type=int, default=0,
                    help="Number of distinct L2 counterparties to investigate with SEC (default: 0)")
    ap.add_argument("--as-of", default=None,
                    help="GLEIF snapshot eligibility date YYYY-MM-DD")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    seed = HelixFact(
        fact_type="COMPANY", value=args.company, identifier=args.cik,
        source="SEED", confidence="HIGH", status="ACCEPTED",
        pivot_eligible=True,
        metadata={"identifiers": {"cik": args.cik}},
    )
    # Capture SEC identity and retrieval diagnostics per research probe.
    # No guessed CIK is acceptable: an unresolved name is explicitly recorded.
    if not args.sec_user_agent:
        print("WARNING: SEC_USER_AGENT missing; SEC requests may be rejected.",
              file=sys.stderr)
    agent = args.sec_user_agent or "CorporationHelix research contact@example.com"

    def fetch(pivot):
        diagnostics = {
            "status": "NO_SEC_IDENTITY",
            "cik": None,
            "identity_method": None,
            "filings_retrieved": 0,
            "sections_retrieved": 0,
        }
        pivot.metadata["sec_probe"] = diagnostics
        supplied = pivot.metadata.get("identifiers", {}).get("cik")
        if supplied:
            cik = str(supplied)
            diagnostics["identity_method"] = "EXPLICIT_CIK"
        elif (pivot.identifier or "").isdigit() and len(pivot.identifier) <= 10:
            cik = pivot.identifier
            diagnostics["identity_method"] = "IDENTIFIER_CIK"
        else:
            cik = resolve_cik_by_name(pivot.value, agent)
            diagnostics["identity_method"] = "SEC_TICKERS_EXACT_NAME"
        if not cik:
            return None
        diagnostics["cik"] = str(cik).zfill(10)
        diagnostics["status"] = "CIK_RESOLVED_FETCH_PENDING"
        data = fetch_ma_filings(cik, agent)
        filings = list((data or {}).get("filings") or [])
        diagnostics["filings_retrieved"] = len(filings)
        diagnostics["sections_retrieved"] = sum(
            len(filing.get("sections") or []) for filing in filings
        )
        diagnostics["status"] = "FILINGS_RETRIEVED" if filings else "NO_SEC_FILINGS"
        return data

    edgar = EdgarMAExpansionProvider(fetch_filings_fn=fetch)
    gleif = GleifRelationshipEvidenceProvider(
        args.lei_index, args.rr_index, as_of_date=args.as_of,
        max_edges=args.max_gleif_edges,
    )
    result, integration = run_integrated(
        seed, edgar, gleif, max_iterations=args.max_iterations,
        max_sec_candidates=args.max_sec_candidates,
    )

    reverse = investigate_l2_leads(
        seed=seed, facts=result.facts, edgar_provider=edgar,
        max_probes=args.gleif_sec_probes,
    )

    if args.json:
        print(json.dumps({
            **result.to_dict(),
            "cross_source": integration,
            "gleif_to_sec_research": reverse,
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
    print(f"L2 leads    : {reverse['leads_found']} ({reverse['leads_probed']} SEC-probed)")
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
    for lead in reverse["leads"]:
        if lead["decision"] == "SEC_TRANSACTION_CANDIDATE_FOUND_REVIEW":
            print(f"  SEC research lead: {lead['related_name']} (REVIEW)")
    if integration["errors"]:
        print(f"GLEIF enrichment errors: {len(integration['errors'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
