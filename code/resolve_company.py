#!/usr/bin/env python3
from __future__ import annotations
import argparse
import json
import sys
import time
from root_entity_resolver import resolve_company_root

STATUS_COLOR = {"AUTO_RESOLVED": "32", "REVIEW_REQUIRED": "33", "NO_MATCH": "31"}


def _c(code: str, text: str) -> str:
    if not sys.stdout.isatty():
        return text
    return f"\033[{code}m{text}\033[0m"


def _print_candidate_row(i: int, c, selected: bool) -> None:
    marker = _c("32;1", " <== SELECTED") if selected else ""
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


def main() -> int:
    ap = argparse.ArgumentParser(description="Resolve a company name to its most likely GLEIF corporate root.")
    ap.add_argument("--company", required=True)
    ap.add_argument("--lei-index", default="data/processed/gleif_lei.sqlite")
    ap.add_argument("--rr-index", default="data/processed/gleif_rr.sqlite")
    ap.add_argument("--seed-limit", type=int, default=100)
    ap.add_argument("--max-depth", type=int, default=12)
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--verbose", "-v", action="store_true",
                     help="Show full per-candidate scoring stats even when AUTO_RESOLVED.")
    args = ap.parse_args()

    started = time.monotonic()
    try:
        result = resolve_company_root(args.company, args.lei_index, args.rr_index, args.seed_limit, args.max_depth)
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        print("hint: build the local GLEIF indexes first, or pass --lei-index/--rr-index "
              "to point at existing ones.", file=sys.stderr)
        return 1
    elapsed_ms = (time.monotonic() - started) * 1000

    if args.json:
        payload = result.to_dict()
        payload["candidates"] = payload["candidates"][:args.top]
        payload["elapsed_ms"] = round(elapsed_ms, 1)
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0 if result.status == "AUTO_RESOLVED" else 2

    status_label = _c(STATUS_COLOR.get(result.status, "0"), result.status)

    print("=" * 72)
    print("CORPORATION HELIX — ROOT ENTITY RESOLUTION")
    print("=" * 72)
    print(f"Query      : {result.query}")
    print(f"Resolution : {status_label}   ({elapsed_ms:.0f} ms)")

    if result.status == "AUTO_RESOLVED" and result.root:
        print(f"Confidence : {result.confidence}")
        print(f"Root       : {result.root.legal_name or '-'}")
        print(f"LEI        : {result.root.lei}")
        print(f"Why        : {result.reason}")
        if args.verbose:
            print(f"\nNAME-MATCHED SEEDS ({len(result.seed_matches)})")
            print("-" * 72)
            for i, seed in enumerate(result.seed_matches[:args.top], 1):
                print(f"[{i}] {seed.get('legal_name')} | {seed.get('lei')} | "
                      f"{seed.get('legal_jurisdiction') or '-'} | {seed.get('entity_status') or '-'} | "
                      f"name={seed.get('name_match', 0):.2f}")
            print(f"\nALL CANDIDATES ({min(len(result.candidates), args.top)})")
            print("-" * 72)
            for i, c in enumerate(result.candidates[:args.top], 1):
                _print_candidate_row(i, c, result.root and c.lei == result.root.lei)
        else:
            print("(run with --verbose to see the full scoring breakdown)")
        return 0

    # NO_MATCH or REVIEW_REQUIRED: this is the "why didn't it just pick one"
    # moment, so show the competing evidence by default rather than hiding it
    # behind --verbose. That transparency is the point of the tool.
    print(f"Reason     : {result.reason}\n")

    print(f"NAME-MATCHED SEEDS ({len(result.seed_matches)})")
    print("-" * 72)
    for i, seed in enumerate(result.seed_matches[:args.top], 1):
        print(f"[{i}] {seed.get('legal_name')} | {seed.get('lei')} | "
              f"{seed.get('legal_jurisdiction') or '-'} | {seed.get('entity_status') or '-'} | "
              f"name={seed.get('name_match', 0):.2f}")

    print(f"\nCOMPETING ROOT CANDIDATES ({min(len(result.candidates), args.top)})")
    print("-" * 72)
    for i, c in enumerate(result.candidates[:args.top], 1):
        _print_candidate_row(i, c, False)

    return 2 if result.status == "REVIEW_REQUIRED" else 3


if __name__ == "__main__":
    raise SystemExit(main())
