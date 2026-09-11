from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))

from domain_candidates import CorporateEntity, candidates_from_observations
from evidence_bridge import bridge_observations
from evidence_contract import EvidenceCapability, identify_evidence_gaps
from parsers.asm_mapping import map_asm_record

ENTITY_LEI = "529900R5WX9N2OI2N910"
ENTITY_NAME = "Sony Corporation"

ENTITY = CorporateEntity(
    entity_name=ENTITY_NAME,
    entity_lei=ENTITY_LEI,
    corporate_confidence="HIGH",
)

def _candidate_for(domain, bridged):
    candidates = candidates_from_observations([ENTITY], bridged)
    return next(c for c in candidates if c.candidate_domain == domain)

def test_realistic_customer_record_two_corroborating_sources_reaches_review_medium():
    observations = map_asm_record(
        {
            "domain": "sony.com",
            "ip.asn": 64500,
            "ip.asn.org": "Sony Corporation",
            "ssl.subject.org": "Sony Corporation",
            "ssl.san": ["www.sony.com", "sony.com"],
        },
        expected_entity_name=ENTITY_NAME,
        provider_prefix="customer-asm",
        reference="asset-001",
    )
    bridged = bridge_observations(
        observations, entity_lei=ENTITY_LEI, entity_name=ENTITY_NAME
    )
    candidate = _candidate_for("sony.com", bridged)

    assert len(observations) == 2
    assert len(bridged) == 2
    assert candidate.disposition.value == "REVIEW"
    assert candidate.infrastructure_attribution_confidence.value == "MEDIUM"

def test_conflicting_supplied_ownership_rejects():
    observations = map_asm_record(
        {
            "domain": "sony.com",
            "ip.asn": 64501,
            "ip.asn.org": "Unrelated Networks LLC",
            "ssl.subject.org": "Sony Corporation",
        },
        expected_entity_name=ENTITY_NAME,
        provider_prefix="customer-asm",
        reference="asset-002",
    )
    bridged = bridge_observations(
        observations, entity_lei=ENTITY_LEI, entity_name=ENTITY_NAME
    )
    candidate = _candidate_for("sony.com", bridged)

    assert candidate.disposition.value == "REJECT"
    assert candidate.infrastructure_attribution_confidence.value == "HIGH"

def test_missing_tls_org_remains_gap_not_positive_evidence():
    observations = map_asm_record(
        {
            "domain": "sony.com",
            "ip.asn": 64502,
            "ip.asn.org": "Sony Corporation",
        },
        expected_entity_name=ENTITY_NAME,
        provider_prefix="customer-asm",
        reference="asset-003",
    )
    tls = [o for o in observations if o.capability is EvidenceCapability.TLS_CERTIFICATE][0]
    assert tls.availability.value == "MISSING"

    bridged = bridge_observations(
        observations, entity_lei=ENTITY_LEI, entity_name=ENTITY_NAME
    )
    assert len(bridged) == 1

    gaps = identify_evidence_gaps("sony.com", observations)
    gap_caps = {g.capability for g in gaps}
    assert EvidenceCapability.TLS_CERTIFICATE in gap_caps

def test_pipeline_never_upgrades_corroboration_to_auto():
    observations = map_asm_record(
        {
            "domain": "sony.com",
            "ip.asn": 64503,
            "ip.asn.org": "Sony Corporation",
            "ssl.subject.org": "Sony Corporation",
        },
        expected_entity_name=ENTITY_NAME,
    )
    bridged = bridge_observations(
        observations, entity_lei=ENTITY_LEI, entity_name=ENTITY_NAME
    )
    candidate = _candidate_for("sony.com", bridged)

    assert candidate.disposition.value != "AUTO"
