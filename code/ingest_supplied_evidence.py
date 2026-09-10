#!/usr/bin/env python3
"""
Corporation Helix -- ingest supplied ASM/customer evidence into domain
attribution decisions. No web search, no live HTML fetch, no network calls
at all: this consumes evidence someone else already collected (per the
Helix/ASM architectural boundary, CORPORATION_HELIX_CONTEXT.md sec 34.3).

Accepts two input formats, auto-detected by file extension:

  --input evidence.json   Vendor-neutral nested JSON (shape below)
  --input evidence.csv    Flat CSV, one row per observation
                           (see code/parsers/csv_parser.py for columns)

JSON shape:

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
    python3 ingest_supplied_evidence.py --input evidence.csv
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from domain_candidates import CorporateEntity, Disposition, build_candidate, candidates_from_observations, print_summary, write_json
from evidence_bridge import bridge_observations
from evidence_contract import EvidenceGap, InfrastructureObservation, identify_evidence_gaps


def load_supplied_evidence(path: Path) -> tuple[list[CorporateEntity], list[dict]]:
    if path.suffix.lower() == ".csv":
        from parsers.csv_parser import load_csv_evidence
        return load_csv_evidence(path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    entities = [CorporateEntity.from_mapping(e) for e in payload.get("entities", [])]
    return entities, payload.get("subjects", [])


def _infra_observations_for_subject(subject: dict) -> list[InfrastructureObservation]:
    domain = subject.get("domain")
    return [
        InfrastructureObservation.from_mapping({**o, "subject": o.get("subject") or domain})
        for o in subject.get("observations", [])
    ]


def build_observation_dicts(subjects: list[dict]) -> list[dict]:
    """Bridge every subject's InfrastructureObservations into plain observation dicts."""
    observations: list[dict] = []
    for subject in subjects:
        entity_lei = subject.get("entity_lei")
        entity_name = subject.get("entity_name")
        infra_obs = _infra_observations_for_subject(subject)
        observations.extend(
            bridge_observations(infra_obs, entity_lei=entity_lei, entity_name=entity_name)
        )
    return observations


def build_gap_report(subjects: list[dict]) -> dict[tuple[str | None, str], list[EvidenceGap]]:
    """
    For every (entity, domain) subject, ask what evidence -- beyond what was
    supplied -- would help move an unsettled attribution forward. This is
    the "we don't go fetch it, we tell you what to go get" half of the
    architecture: identify_evidence_gaps() already existed in
    evidence_contract.py but was never wired into the actual pipeline
    output until now.
    """
    report: dict[tuple[str | None, str], list[EvidenceGap]] = {}
    for subject in subjects:
        entity_lei = subject.get("entity_lei")
        domain = subject.get("domain")
        if not domain:
            continue
        report[(entity_lei, domain)] = identify_evidence_gaps(domain, _infra_observations_for_subject(subject))
    return report


def print_summary_with_gaps(candidates, gap_report) -> None:
    counts = {d: 0 for d in Disposition}
    for c in candidates:
        counts[c.disposition] += 1

    print("=" * 72)
    print("CORPORATION HELIX - DOMAIN CANDIDATES")
    print("=" * 72)
    print(
        f"Total: {len(candidates)} | "
        f"AUTO: {counts[Disposition.AUTO]} | "
        f"REVIEW: {counts[Disposition.REVIEW]} | "
        f"REJECT: {counts[Disposition.REJECT]}"
    )

    for c in candidates:
        print("-" * 72)
        print(c.candidate_domain)
        print(f"  Entity        : {c.entity_name}")
        print(f"  LEI           : {c.entity_lei or 'UNKNOWN'}")
        print(f"  Relationships : {', '.join(c.relationships) or 'NONE'}")
        print(f"  Corporate conf: {c.corporate_confidence}")
        print(f"  Infra conf    : {c.infrastructure_attribution_confidence.value}")
        print(f"  Disposition   : {c.disposition.value}")
        print(f"  Evidence      : {len(c.evidence)}")
        if c.review_reason:
            print(f"  Reason        : {c.review_reason}")
        if c.disposition is not Disposition.AUTO:
            print_gaps_for_candidate(c, gap_report)


def print_gaps_for_candidate(candidate, gap_report) -> None:
    key = (candidate.entity_lei, candidate.candidate_domain)
    gaps = gap_report.get(key, [])
    if not gaps:
        return
    print("  Evidence gaps (what would help move this forward):")
    for gap in sorted(gaps, key=lambda g: g.priority):
        print(f"    {gap.priority}. [{gap.capability.value}] {gap.request}  ({gap.reason})")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--input", required=True, type=Path, help="Supplied evidence JSON (see module docstring for shape)")
    ap.add_argument("--out", type=Path, default=None, help="Optional: write full candidate JSON here")
    ap.add_argument("--json", action="store_true", help="Print JSON instead of the human-readable summary")
    args = ap.parse_args()

    entities, subjects = load_supplied_evidence(args.input)
    observations = build_observation_dicts(subjects)
    candidates = candidates_from_observations(entities, observations)
    gap_report = build_gap_report(subjects)

    if args.out:
        write_json(args.out, candidates)

    if args.json:
        payload = []
        for c in candidates:
            d = c.to_dict()
            d["evidence_gaps"] = [g.to_dict() for g in gap_report.get((c.entity_lei, c.candidate_domain), [])]
            payload.append(d)
        print(json.dumps(payload, indent=2, ensure_ascii=False))
    else:
        print_summary_with_gaps(candidates, gap_report)
        if args.out:
            print(f"\nWrote: {args.out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
