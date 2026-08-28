from __future__ import annotations

import argparse
import json
from pathlib import Path

from .providers.gleif import load_lei_file, load_relationship_file
from .providers.edgar import load_edgar_exhibit
from .providers.rdap import fetch_domain, load_rdap_file
from .resolution.matcher import rank_candidates


def cmd_normalize_gleif(args: argparse.Namespace) -> None:
    entities = load_lei_file(args.input)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w") as f:
        for entity in entities:
            f.write(json.dumps(entity.to_dict(), ensure_ascii=False) + "\n")
    print(f"Wrote {len(entities)} normalized GLEIF entities to {out}")


def cmd_match_domain(args: argparse.Namespace) -> None:
    entities = load_lei_file(args.gleif)
    infra = load_rdap_file(args.rdap_file) if args.rdap_file else fetch_domain(args.domain)
    matches = rank_candidates(infra, entities, args.limit)
    result = {
        "domain": infra.resource,
        "rdap_organizations": infra.organization_names,
        "rdap_addresses": [a.compact() for a in infra.addresses],
        "candidates": [m.to_dict() for m in matches],
        "note": "Candidate resolution only. This does not assert corporate ownership; corroborate with GLEIF Level 2, EDGAR, or another ownership source.",
    }
    print(json.dumps(result, indent=2, ensure_ascii=False))



def cmd_normalize_edgar(args: argparse.Namespace) -> None:
    entities, relationships = load_edgar_exhibit(args.input)
    result = {
        "entities": [e.to_dict() for e in entities],
        "relationships": [r.to_dict() for r in relationships],
    }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False))
    print(f"Wrote {len(entities)} EDGAR entities and {len(relationships)} assertions to {out}")


def cmd_relationships(args: argparse.Namespace) -> None:
    relationships = load_relationship_file(args.input)
    print(json.dumps([r.to_dict() for r in relationships], indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="corphelix")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p = sub.add_parser("normalize-edgar", help="Normalize existing EDGAR Exhibit 21 output")
    p.add_argument("--input", required=True)
    p.add_argument("--out", required=True)
    p.set_defaults(func=cmd_normalize_edgar)

    p = sub.add_parser("normalize-gleif", help="Normalize a GLEIF Level 1 JSON file to JSONL")
    p.add_argument("--input", required=True)
    p.add_argument("--out", required=True)
    p.set_defaults(func=cmd_normalize_gleif)

    p = sub.add_parser("match-domain", help="Map RDAP registrant evidence to candidate GLEIF entities")
    p.add_argument("--gleif", required=True, help="GLEIF Level 1 JSON input")
    source = p.add_mutually_exclusive_group(required=True)
    source.add_argument("--domain", help="Live RDAP lookup")
    source.add_argument("--rdap-file", help="Saved RDAP JSON response")
    p.add_argument("--limit", type=int, default=10)
    p.set_defaults(func=cmd_match_domain)

    p = sub.add_parser("show-gleif-relationships", help="Parse GLEIF Level 2 relationship JSON")
    p.add_argument("--input", required=True)
    p.set_defaults(func=cmd_relationships)
    return parser


def main() -> None:
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
