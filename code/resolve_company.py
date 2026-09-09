#!/usr/bin/env python3
from __future__ import annotations
import argparse
import json
from root_entity_resolver import resolve_company_root


def main() -> int:
    ap = argparse.ArgumentParser(description="Resolve a company name to its most likely GLEIF corporate root.")
    ap.add_argument("--company", required=True)
    ap.add_argument("--lei-index", default="data/processed/gleif_lei.sqlite")
    ap.add_argument("--rr-index", default="data/processed/gleif_rr.sqlite")
    ap.add_argument("--seed-limit", type=int, default=100)
    ap.add_argument("--max-depth", type=int, default=12)
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    result = resolve_company_root(args.company, args.lei_index, args.rr_index, args.seed_limit, args.max_depth)
    if args.json:
        payload = result.to_dict(); payload["candidates"] = payload["candidates"][:args.top]
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0 if result.status == "AUTO_RESOLVED" else 2

    print("=" * 72)
    print("CORPORATION HELIX — M4.3D ROOT ENTITY RESOLUTION")
    print("=" * 72)
    print(f"Query      : {result.query}")
    print(f"Resolution : {result.status}")
    print(f"Confidence : {result.confidence}")
    print(f"Reason     : {result.reason}\n")

    print(f"NAME-MATCHED SEEDS ({len(result.seed_matches)})")
    print("-" * 72)
    for i, seed in enumerate(result.seed_matches[:args.top], 1):
        print(f"[{i}] {seed.get('legal_name')} | {seed.get('lei')} | {seed.get('legal_jurisdiction') or '-'} | {seed.get('entity_status') or '-'} | name={seed.get('name_match',0):.2f}")

    print(f"\nROOT CANDIDATES ({min(len(result.candidates), args.top)})")
    print("-" * 72)
    for i, c in enumerate(result.candidates[:args.top], 1):
        marker = " <== SELECTED" if result.root and c.lei == result.root.lei else ""
        print(f"[{i}] {c.legal_name or c.lei}{marker}")
        print(f"    LEI              : {c.lei}")
        print(f"    Jurisdiction     : {c.jurisdiction or '-'}")
        print(f"    Status           : {c.entity_status or '-'}")
        print(f"    Coverage         : {c.matched_seed_count}/{c.total_seed_count} ({c.coverage:.0%})")
        print(f"    Ultimate votes   : {c.ultimate_parent_votes}")
        print(f"    Direct votes     : {c.direct_parent_votes}")
        print(f"    Terminal votes   : {c.terminal_votes}")
        print(f"    Max upward depth : {c.max_depth}")
        print(f"    Name match       : {c.name_match:.2f}")
        print(f"    Score            : {c.score:.2f}\n")

    if result.status == "AUTO_RESOLVED" and result.root:
        print("MACHINE-USABLE ROOT")
        print("-" * 72)
        print(f"Name : {result.root.legal_name or '-'}")
        print(f"LEI  : {result.root.lei}")
    return 0 if result.status == "AUTO_RESOLVED" else 2


if __name__ == "__main__":
    raise SystemExit(main())
