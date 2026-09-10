#!/usr/bin/env python3
"""
Corporation Helix -- ingest supplied ASM/customer evidence into domain
attribution decisions. No web search, no live HTML fetch, no network calls
at all: this consumes evidence someone else already collected (per the
Helix/ASM architectural boundary, CORPORATION_HELIX_CONTEXT.md sec 34.3).

Input format (vendor-neutral -- write a thin adapter to produce this from
whatever your ASM tool or sqlite table actually looks like):

{
  "entities": [
    {"entity_lei": "...", "entity_name": "..."}
  ],
  "subjects": [
    {
      "entity_lei": "...",
      "domain": "example.com",
      "observations": [
        {"capability": "RDAP_WHOIS", "provider": "asm-tool", "availability": "PROVIDED",
         "observed_value": "Example Corp", "supports_attribution": true},
        {"capability": "IP_ASN_OWNERSHIP", "provider": "asm-tool", "availability": "INCONCLUSIVE",
         "observed_value": "AS16509 (Amazon)"}
      ]
    }
  ]
}

Usage:
    python3 ingest_supplied_evidence.py --input evidence.json [--out candidates.json] [--json]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from domain_candidates import CorporateEntity, build_candidate, candidates_from_observations, print_summary, write_json
from evidence_bridge import bridge_observations
from evidence_contract import InfrastructureObservation


def load_supplied_evidence(path: Path) -> tuple[list[CorporateEntity], list[dict]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    entities = [CorporateEntity.from_mapping(e) for e in payload.get("entities", [])]
    return entities, payload.get("subjects", [])


def build_observation_dicts(subjects: list[dict]) -> list[dict]:
    """Bridge every subject's InfrastructureObservations into plain observation dicts."""
    observations: list[dict] = []
    for subject in subjects:
        entity_lei = subject.get("entity_lei")
        entity_name = subject.get("entity_name")
        domain = subject.get("domain")
        raw_obs = subject.get("observations", [])

        infra_obs = [
            InfrastructureObservation.from_mapping({**o, "subject": o.get("subject") or domain})
            for o in raw_obs
        ]
        observations.extend(
            bridge_observations(infra_obs, entity_lei=entity_lei, entity_name=entity_name)
        )
    return observations


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", required=True, type=Path, help="Supplied evidence JSON (see module docstring for shape)")
    ap.add_argument("--out", type=Path, default=None, help="Optional: write full candidate JSON here")
    ap.add_argument("--json", action="store_true", help="Print JSON instead of the human-readable summary")
    args = ap.parse_args()

    entities, subjects = load_supplied_evidence(args.input)
    observations = build_observation_dicts(subjects)
    candidates = candidates_from_observations(entities, observations)

    if args.out:
        write_json(args.out, candidates)

    if args.json:
        print(json.dumps([c.to_dict() for c in candidates], indent=2, ensure_ascii=False))
    else:
        print_summary(candidates)
        if args.out:
            print(f"\nWrote: {args.out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
