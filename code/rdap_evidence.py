#!/usr/bin/env python3
from __future__ import annotations

"""Interpret RDAP observations as M4.3B DomainEvidence.

Recovered matcher policy is preserved conceptually:
- name similarity gets a candidate into consideration;
- a second structured signal (address or country) is required for a strong match;
- structured conflicts reject the RDAP attribution assertion.

Raw RDAP org/registrant observations are always preserved independently from the
interpreted assertion.
"""

import argparse
import json
import re
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from domain_candidates import CorporateEntity, DomainEvidence, EvidenceType, load_entities
from providers.domain_rdap import RdapDomainObservation, fetch_domain, load_rdap_file


LEGAL_FORMS = {
    "inc", "incorporated", "corp", "corporation", "llc", "ltd", "limited",
    "plc", "gmbh", "bv", "b v", "srl", "s r l", "sa", "s a", "s l", "sas",
    "aps", "kk", "k k", "pte", "pty", "sp z oo", "sp z o o", "private limited",
}


def _ascii(text: str) -> str:
    text = unicodedata.normalize("NFKD", text)
    return "".join(c for c in text if not unicodedata.combining(c))


def normalize_name(name: str | None, strip_legal_form: bool = True) -> str:
    if not name:
        return ""
    text = _ascii(name).lower().replace("&", " and ")
    text = re.sub(r"\([^)]*(?:dormant|non[- ]operational)[^)]*\)", " ", text)
    text = re.sub(r"\(fka\s+[^)]*\)", " ", text)
    text = re.sub(r"[^a-z0-9]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    if not strip_legal_form:
        return text
    changed = True
    while changed and text:
        changed = False
        for suffix in sorted(LEGAL_FORMS, key=len, reverse=True):
            if text == suffix:
                return ""
            if text.endswith(" " + suffix):
                text = text[: -(len(suffix) + 1)].strip()
                changed = True
                break
    return text


def _sim(a: str, b: str) -> float:
    return SequenceMatcher(None, a, b).ratio() if a and b else 0.0


def _country_score(rdap_country: str | None, jurisdiction: str | None) -> float | None:
    if not rdap_country or not jurisdiction:
        return None
    left = rdap_country.upper()
    right = jurisdiction.upper()
    return 1.0 if left in right or right in left else 0.0


def interpret_rdap(entity: CorporateEntity, rdap: RdapDomainObservation) -> list[DomainEvidence]:
    evidence: list[DomainEvidence] = []
    reference = rdap.source_url

    # Raw facts are evidence observations, not automatic ownership assertions.
    for org in rdap.organization_names:
        evidence.append(DomainEvidence(
            provider="RDAP",
            evidence_type=EvidenceType.RDAP_ORG,
            reference=reference,
            observed_value=org,
            subject_name=entity.entity_name,
            subject_identifier=entity.entity_lei,
            supports_attribution=True,
            raw={"kind": "registrant_name_or_org"},
        ))

    if not rdap.organization_names:
        return evidence

    entity_name = normalize_name(entity.entity_name)
    name_score = max((_sim(normalize_name(x), entity_name) for x in rdap.organization_names), default=0.0)
    country_score = _country_score(rdap.country, entity.jurisdiction)

    # Current Helix operator export does not yet carry entity addresses, so the
    # first M4.3B bridge can only use recovered name + jurisdiction logic. We
    # preserve this limitation explicitly rather than inventing address support.
    has_structured_support = country_score == 1.0
    has_structured_conflict = country_score == 0.0

    detail: dict[str, Any] = {
        "name_score": round(name_score, 4),
        "rdap_country": rdap.country,
        "entity_jurisdiction": entity.jurisdiction,
        "country_score": country_score,
        "matcher_version": "recovered-rdap-matcher-adapter-v1",
    }

    if name_score >= 0.90 and has_structured_support and not has_structured_conflict:
        evidence.append(DomainEvidence(
            provider="RDAP_INTERPRETER",
            evidence_type=EvidenceType.RDAP_ATTRIBUTION_MATCH,
            reference=reference,
            observed_value=max(rdap.organization_names, key=lambda x: _sim(normalize_name(x), entity_name)),
            subject_name=entity.entity_name,
            subject_identifier=entity.entity_lei,
            supports_attribution=True,
            raw=detail,
        ))
    elif has_structured_conflict and name_score >= 0.65:
        evidence.append(DomainEvidence(
            provider="RDAP_INTERPRETER",
            evidence_type=EvidenceType.RDAP_ATTRIBUTION_CONFLICT,
            reference=reference,
            observed_value="; ".join(rdap.organization_names),
            subject_name=entity.entity_name,
            subject_identifier=entity.entity_lei,
            supports_attribution=False,
            raw=detail,
        ))

    return evidence


def _entity_by_lei(entities: list[CorporateEntity], lei: str) -> CorporateEntity:
    matches = [e for e in entities if e.entity_lei == lei]
    if len(matches) != 1:
        raise ValueError(f"Expected exactly one entity for LEI {lei!r}; found {len(matches)}")
    return matches[0]


def main() -> int:
    ap = argparse.ArgumentParser(description="Create M4.3B evidence observations from RDAP.")
    ap.add_argument("--entities", required=True, type=Path)
    ap.add_argument("--entity-lei", required=True)
    ap.add_argument("--domain")
    ap.add_argument("--rdap-file", type=Path)
    ap.add_argument("--out", required=True, type=Path)
    args = ap.parse_args()

    if bool(args.domain) == bool(args.rdap_file):
        ap.error("provide exactly one of --domain or --rdap-file")

    entities = load_entities(args.entities)
    entity = _entity_by_lei(entities, args.entity_lei)
    rdap = load_rdap_file(args.rdap_file) if args.rdap_file else fetch_domain(args.domain)
    observations = []
    for e in interpret_rdap(entity, rdap):
        item = {
            "entity_lei": entity.entity_lei,
            "entity_name": entity.entity_name,
            "domain": rdap.domain or args.domain,
            "provider": e.provider,
            "evidence_type": e.evidence_type.value,
            "reference": e.reference,
            "observed_value": e.observed_value,
            "subject_name": e.subject_name,
            "subject_identifier": e.subject_identifier,
            "supports_attribution": e.supports_attribution,
            "raw": e.raw,
        }
        observations.append(item)

    payload = {"observations": observations}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"RDAP domain: {rdap.domain}")
    print(f"Registrant org/name values: {len(rdap.organization_names)}")
    print(f"Evidence observations: {len(observations)}")
    print(f"Wrote: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
