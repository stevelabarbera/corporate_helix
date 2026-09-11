#!/usr/bin/env python3
"""
Corporation Helix -- M4.3E phase 2: InfrastructureObservation -> DomainEvidence
bridge.

Supplied evidence subjects are not always domains. IP/ASN evidence preserves
its native subject and may carry an associated candidate domain in
raw["candidate_domain"]. Nothing in this module makes a network call.
"""
from __future__ import annotations

from typing import Any, Iterable

from evidence_contract import EvidenceAvailability, EvidenceCapability, InfrastructureObservation
from domain_candidates import EvidenceType

_CAPABILITY_MAP: dict[EvidenceCapability, tuple[EvidenceType, EvidenceType]] = {
    EvidenceCapability.RDAP_WHOIS: (EvidenceType.RDAP_REGISTRANT, EvidenceType.RDAP_ATTRIBUTION_CONFLICT),
    EvidenceCapability.IP_ASN_OWNERSHIP: (EvidenceType.ASN_OWNERSHIP, EvidenceType.CONTRADICTORY_OWNERSHIP),
    EvidenceCapability.TLS_CERTIFICATE: (EvidenceType.CERTIFICATE_ORG, EvidenceType.CONTRADICTORY_OWNERSHIP),
    EvidenceCapability.DNS: (EvidenceType.DNS_OBSERVATION, EvidenceType.CONTRADICTORY_OWNERSHIP),
    EvidenceCapability.HTTP_LEGAL_PRIVACY: (EvidenceType.LEGAL_PRIVACY_DECLARATION, EvidenceType.CONTRADICTORY_OWNERSHIP),
    EvidenceCapability.CUSTOMER_ASSERTION: (EvidenceType.CUSTOMER_SUPPLIED, EvidenceType.CONTRADICTORY_OWNERSHIP),
}


def observation_to_domain_evidence(
    obs: InfrastructureObservation,
    *,
    entity_lei: str | None = None,
    entity_name: str | None = None,
) -> dict[str, Any] | None:
    if obs.availability in (EvidenceAvailability.MISSING, EvidenceAvailability.INCONCLUSIVE):
        return None

    positive_type, negative_type = _CAPABILITY_MAP.get(
        obs.capability, (EvidenceType.OTHER, EvidenceType.CONTRADICTORY_OWNERSHIP)
    )
    is_negative = (
        obs.availability is EvidenceAvailability.CONTRADICTORY
        or obs.supports_attribution is False
    )
    evidence_type = negative_type if is_negative else positive_type

    candidate_domain = obs.raw.get("candidate_domain") or obs.subject

    return {
        "entity_lei": entity_lei,
        "entity_name": entity_name,
        "domain": candidate_domain,
        "provider": obs.provider,
        "evidence_type": evidence_type.value,
        "reference": obs.reference,
        "observed_value": obs.observed_value,
        "supports_attribution": not is_negative,
        "raw": dict(obs.raw),
    }


def bridge_observations(
    observations: Iterable[InfrastructureObservation],
    *,
    entity_lei: str | None = None,
    entity_name: str | None = None,
) -> list[dict[str, Any]]:
    out = []
    for obs in observations:
        bridged = observation_to_domain_evidence(
            obs, entity_lei=entity_lei, entity_name=entity_name
        )
        if bridged is not None:
            out.append(bridged)
    return out
