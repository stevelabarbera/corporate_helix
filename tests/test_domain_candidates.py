import json
import sys
from pathlib import Path

# Allow running directly from repo root:
# python3 tests/test_domain_candidates.py
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "code"))

from domain_candidates import (  # noqa: E402
    CorporateEntity,
    Disposition,
    DomainEvidence,
    EvidenceType,
    InfrastructureConfidence,
    build_candidate,
    candidates_from_observations,
    normalize_domain,
)


def entity() -> CorporateEntity:
    return CorporateEntity(
        entity_name="SONY EUROPE B.V.",
        entity_lei="5493003AP2HY7BTV8H64",
        relationships=["DIRECT_ACCOUNTING_CHILD", "ULTIMATE_ACCOUNTING_CHILD"],
        corporate_confidence="HIGH",
        jurisdiction="NL",
        source="GLEIF",
    )


def test_no_evidence_is_review_unknown():
    c = build_candidate(entity(), "sony.example", [])
    assert c.disposition is Disposition.REVIEW
    assert c.infrastructure_attribution_confidence is InfrastructureConfidence.UNKNOWN


def test_identity_grade_evidence_is_auto():
    ev = DomainEvidence(
        provider="official-site",
        evidence_type=EvidenceType.OFFICIAL_WEBSITE,
        reference="fixture:official-site",
    )
    c = build_candidate(entity(), "sony.example", [ev])
    assert c.disposition is Disposition.AUTO
    assert c.infrastructure_attribution_confidence is InfrastructureConfidence.HIGH


def test_one_corroborating_signal_is_review_low():
    ev = DomainEvidence(
        provider="ct",
        evidence_type=EvidenceType.CERTIFICATE_DOMAIN,
        reference="fixture:ct",
    )
    c = build_candidate(entity(), "sony.example", [ev])
    assert c.disposition is Disposition.REVIEW
    assert c.infrastructure_attribution_confidence is InfrastructureConfidence.LOW


def test_two_corroborating_types_are_review_medium():
    evs = [
        DomainEvidence(
            provider="ct",
            evidence_type=EvidenceType.CERTIFICATE_DOMAIN,
            reference="fixture:ct",
        ),
        DomainEvidence(
            provider="edgar",
            evidence_type=EvidenceType.EDGAR_REFERENCE,
            reference="fixture:edgar",
        ),
    ]
    c = build_candidate(entity(), "sony.example", evs)
    assert c.disposition is Disposition.REVIEW
    assert c.infrastructure_attribution_confidence is InfrastructureConfidence.MEDIUM


def test_contradictory_ownership_rejects():
    evs = [
        DomainEvidence(
            provider="ct",
            evidence_type=EvidenceType.CERTIFICATE_DOMAIN,
            reference="fixture:ct",
        ),
        DomainEvidence(
            provider="rdap",
            evidence_type=EvidenceType.CONTRADICTORY_OWNERSHIP,
            reference="fixture:rdap",
            supports_attribution=False,
        ),
    ]
    c = build_candidate(entity(), "sony.example", evs)
    assert c.disposition is Disposition.REJECT


def test_corporate_high_does_not_make_domain_auto():
    c = build_candidate(entity(), "sony.example", [])
    assert c.corporate_confidence == "HIGH"
    assert c.disposition is Disposition.REVIEW


def test_observations_group_by_entity_and_domain():
    entities = [entity()]
    observations = [
        {
            "entity_lei": "5493003AP2HY7BTV8H64",
            "domain": "https://www.sony.example/about",
            "provider": "ct",
            "evidence_type": "CERTIFICATE_DOMAIN",
            "reference": "fixture:ct",
        },
        {
            "entity_lei": "5493003AP2HY7BTV8H64",
            "domain": "www.sony.example",
            "provider": "edgar",
            "evidence_type": "EDGAR_REFERENCE",
            "reference": "fixture:edgar",
        },
    ]
    candidates = candidates_from_observations(entities, observations)
    assert len(candidates) == 1
    assert candidates[0].candidate_domain == "www.sony.example"
    assert len(candidates[0].evidence) == 2
    assert candidates[0].disposition is Disposition.REVIEW
    assert (
        candidates[0].infrastructure_attribution_confidence
        is InfrastructureConfidence.MEDIUM
    )


def test_normalize_domain():
    assert normalize_domain("HTTPS://Example.COM/a") == "example.com"


TESTS = [
    test_no_evidence_is_review_unknown,
    test_identity_grade_evidence_is_auto,
    test_one_corroborating_signal_is_review_low,
    test_two_corroborating_types_are_review_medium,
    test_contradictory_ownership_rejects,
    test_corporate_high_does_not_make_domain_auto,
    test_observations_group_by_entity_and_domain,
    test_normalize_domain,
]


if __name__ == "__main__":
    failures = []
    for test in TESTS:
        try:
            test()
            print(f"PASS {test.__name__}")
        except Exception as exc:
            failures.append((test.__name__, exc))
            print(f"FAIL {test.__name__}: {exc}")

    print()
    print(f"{len(TESTS) - len(failures)} passed / {len(failures)} failed")
    raise SystemExit(1 if failures else 0)
