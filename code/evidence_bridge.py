#!/usr/bin/env python3
"""
Corporation Helix -- M4.3E phase 2: InfrastructureObservation -> DomainEvidence
bridge.

This is the piece named as "NEXT" in CORPORATION_HELIX_CONTEXT.md sec 34.10:

    supplied ASM/customer observations
            ->
    InfrastructureObservation
            ->
    bridge / normalize into DomainEvidence
            ->
    existing M4.3B deterministic attribution policy
            ->
    DomainCandidate
            ->
    AUTO / REVIEW / REJECT

It exists specifically so Helix never has to re-fetch or re-derive evidence
that ASM/the customer already collected (sec 34.3's architectural boundary).
Nothing in this module makes a network call.

Capability -> EvidenceType mapping (deliberately conservative -- a raw
supplied capability observation lands in the CORROBORATING tier, not
IDENTITY_GRADE, except CUSTOMER_ASSERTION, which is the one capability that
represents the customer/operator directly telling Helix "this is ours" --
consistent with the project's hybrid model ranking user-supplied data above
Helix's own inference):

    RDAP_WHOIS          -> RDAP_REGISTRANT          (corroborating)
    IP_ASN_OWNERSHIP     -> ASN_OWNERSHIP            (corroborating)
    TLS_CERTIFICATE      -> CERTIFICATE_ORG          (corroborating)
    DNS                  -> DNS_OBSERVATION          (corroborating)
    HTTP_LEGAL_PRIVACY    -> LEGAL_PRIVACY_DECLARATION (corroborating)
    CUSTOMER_ASSERTION    -> CUSTOMER_SUPPLIED        (identity-grade)

MISSING and INCONCLUSIVE observations produce no DomainEvidence at all --
they carry no information usable by evaluate_evidence() either way. That
information isn't lost; it's exactly what evidence_contract.identify_evidence_gaps
already tracks separately. Conflating "we don't have this" with "this
doesn't support attribution" was the gap named in CORPORATION_HELIX_CONTEXT.md
sec 34.6-34.7 ("An evidence request is not evidence... Contradictory evidence
is deliberately not reported as merely missing"); this bridge keeps that
distinction intact by simply not manufacturing a DomainEvidence record for
either MISSING or INCONCLUSIVE.
"""
from __future__ import annotations

from typing import Any, Iterable

from evidence_contract import EvidenceAvailability, EvidenceCapability, InfrastructureObservation
from domain_candidates import EvidenceType

_CAPABILITY_MAP: dict[EvidenceCapability, tuple[EvidenceType, EvidenceType]] = {
    # capability: (positive EvidenceType, negative/contradictory EvidenceType)
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
    """
    Convert one supplied InfrastructureObservation into the plain observation
    dict shape domain_candidates.candidates_from_observations() already
    consumes. Returns None for MISSING/INCONCLUSIVE observations -- there is
    nothing for the attribution policy to evaluate either way.
    """
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

    return {
        "entity_lei": entity_lei,
        "entity_name": entity_name,
        "domain": obs.subject,
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
    """Bridge a batch of InfrastructureObservations for one (entity, domain) subject."""
    out = []
    for obs in observations:
        bridged = observation_to_domain_evidence(obs, entity_lei=entity_lei, entity_name=entity_name)
        if bridged is not None:
            out.append(bridged)
    return out
