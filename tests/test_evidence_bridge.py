#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))

from evidence_bridge import bridge_observations, observation_to_domain_evidence
from evidence_contract import InfrastructureObservation
from domain_candidates import EvidenceType


def _obs(capability, availability="PROVIDED", supports_attribution=None, **kw):
    return InfrastructureObservation.from_mapping({
        "capability": capability,
        "provider": "asm-tool",
        "subject": "example.com",
        "availability": availability,
        "supports_attribution": supports_attribution,
        **kw,
    })


def test_missing_produces_no_evidence():
    result = observation_to_domain_evidence(_obs("RDAP_WHOIS", availability="MISSING"))
    assert result is None
    print("PASS test_missing_produces_no_evidence")


def test_inconclusive_produces_no_evidence():
    # This is the case named in CONTEXT.md sec 34.5: a cloud-provider ASN is
    # "generally inconclusive for ownership" -- it must not silently become
    # a phantom positive OR negative signal, just absent from evaluation.
    result = observation_to_domain_evidence(_obs("IP_ASN_OWNERSHIP", availability="INCONCLUSIVE"))
    assert result is None
    print("PASS test_inconclusive_produces_no_evidence")


def test_provided_positive_maps_to_corroborating_type():
    result = observation_to_domain_evidence(_obs("RDAP_WHOIS", supports_attribution=True))
    assert result["evidence_type"] == EvidenceType.RDAP_REGISTRANT.value
    assert result["supports_attribution"] is True
    print("PASS test_provided_positive_maps_to_corroborating_type")


def test_customer_assertion_maps_to_identity_grade():
    result = observation_to_domain_evidence(_obs("CUSTOMER_ASSERTION", supports_attribution=True))
    assert result["evidence_type"] == EvidenceType.CUSTOMER_SUPPLIED.value
    print("PASS test_customer_assertion_maps_to_identity_grade")


def test_contradictory_maps_to_negative_type():
    result = observation_to_domain_evidence(_obs("RDAP_WHOIS", availability="CONTRADICTORY"))
    assert result["evidence_type"] == EvidenceType.RDAP_ATTRIBUTION_CONFLICT.value
    assert result["supports_attribution"] is False
    print("PASS test_contradictory_maps_to_negative_type")


def test_explicit_supports_attribution_false_is_negative_even_when_provided():
    # A customer can supply "I checked, this is NOT ours" without the
    # observation itself being flagged CONTRADICTORY at the availability level.
    result = observation_to_domain_evidence(_obs("IP_ASN_OWNERSHIP", availability="PROVIDED", supports_attribution=False))
    assert result["evidence_type"] == EvidenceType.CONTRADICTORY_OWNERSHIP.value
    assert result["supports_attribution"] is False
    print("PASS test_explicit_supports_attribution_false_is_negative_even_when_provided")


def test_bridge_batch_filters_none_results():
    observations = [
        _obs("RDAP_WHOIS", supports_attribution=True),
        _obs("TLS_CERTIFICATE", availability="INCONCLUSIVE"),
        _obs("IP_ASN_OWNERSHIP", availability="MISSING"),
    ]
    bridged = bridge_observations(observations, entity_lei="LEI-X", entity_name="Example Inc.")
    assert len(bridged) == 1
    assert bridged[0]["entity_lei"] == "LEI-X"
    assert bridged[0]["domain"] == "example.com"
    print("PASS test_bridge_batch_filters_none_results")


if __name__ == "__main__":
    suite = [
        test_missing_produces_no_evidence,
        test_inconclusive_produces_no_evidence,
        test_provided_positive_maps_to_corroborating_type,
        test_customer_assertion_maps_to_identity_grade,
        test_contradictory_maps_to_negative_type,
        test_explicit_supports_attribution_false_is_negative_even_when_provided,
        test_bridge_batch_filters_none_results,
    ]
    failed = 0
    for test in suite:
        try:
            test()
        except Exception as exc:
            failed += 1
            print(f"FAIL {test.__name__}: {exc}")
    print(f"{len(suite)-failed} passed / {failed} failed")
    raise SystemExit(1 if failed else 0)
