#!/usr/bin/env python3
"""Review-only alias-aware company resolution against a COMPLETE Level 1 evidence DB."""
import argparse
import json

from root_entity_resolver import resolve_company_root


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--company", required=True)
    ap.add_argument("--lei-db", default="data/processed/gleif_lei.sqlite")
    ap.add_argument("--rr-db", default="data/processed/gleif_rr.sqlite")
    ap.add_argument("--alias-db", required=True, help="Complete Level 1 staged evidence SQLite")
    ap.add_argument("--as-of-date", help="YYYY-MM-DD")
    ap.add_argument("--allow-sample-aliases", action="store_true",
                    help="Test incomplete evidence; no-match is INSUFFICIENT_EVIDENCE")
    args = ap.parse_args()
    result = resolve_company_root(
        args.company, lei_db=args.lei_db, rr_db=args.rr_db,
        alias_db=args.alias_db, as_of_date=args.as_of_date,
        allow_sample_aliases=args.allow_sample_aliases,
    )
    print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
