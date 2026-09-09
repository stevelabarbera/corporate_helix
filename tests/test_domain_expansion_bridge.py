#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "code"))

from domain_candidates import (
    CorporateEntity,
    DomainEvidence,
    EvidenceType,
    build_candidate,
)
from expansion_bridges import (
    DomainCandidateExpansionProvider,
    domain_candidate_to_fact,
    related_entity_to_fact,
)
from iterative_expansion import run_expansion


def entity(corporate_confidence="HIGH"):
    return CorporateEntity(
        entity_name="HAWK-EYE INNOVATIONS LIMITED",
        entity_lei="549300PBW7OURNSVGL39",
        relationships=["ULTIMATE_ACCOUNTING_CHILD"],
        corporate_confidence=corporate_confidence,
        jurisdiction="GB",
        source="GLEIF",
    )


def ev(kind, supports=True):
    return DomainEvidence(
        provider="TEST",
        evidence_type=kind,
        reference="https://example.test/evidence",
        observed_value="hawkeyeinnovations.com",
        subject_name="HAWK-EYE INNOVATIONS LIMITED",
        subject_identifier="549300PBW7OURNSVGL39",
        supports_attribution=supports,
    )


def test_auto_high_domain_becomes_recursive_pivot():
    candidate = build_candidate(
        entity(),
        "hawkeyeinnovations.com",
        [ev(EvidenceType.OFFICIAL_WEBSITE)],
    )
    fact = domain_candidate_to_fact(candidate)
    assert fact.fact_type == "DOMAIN"
    assert fact.status == "ACCEPTED"
    assert fact.confidence == "HIGH"
    assert fact.can_pivot()
    assert fact.metadata["infrastructure_attribution_confidence"] == "HIGH"


def test_review_domain_is_preserved_but_not_recursive():
    candidate = build_candidate(
        entity(),
        "hawkeyeinnovations.com",
        [ev(EvidenceType.CERTIFICATE_ORG)],
    )
    fact = domain_candidate_to_fact(candidate)
    assert fact.status == "REVIEW"
    assert fact.confidence in {"LOW", "MEDIUM", "UNKNOWN"}
    assert not fact.can_pivot()


def test_rejected_domain_is_preserved_and_blocked():
    candidate = build_candidate(
        entity(),
        "hawkeyeinnovations.com",
        [ev(EvidenceType.CONTRADICTORY_OWNERSHIP, supports=False)],
    )
    fact = domain_candidate_to_fact(candidate)
    assert fact.status == "REJECTED"
    assert not fact.can_pivot()


def test_high_corporate_confidence_cannot_promote_domain():
    candidate = build_candidate(entity("HIGH"), "hawkeyeinnovations.com", [])
    fact = domain_candidate_to_fact(candidate)
    assert fact.metadata["corporate_confidence"] == "HIGH"
    assert fact.status == "REVIEW"
    assert fact.confidence == "UNKNOWN"
    assert not fact.can_pivot()


def test_provider_adds_domain_fact_but_only_auto_reenters_frontier():
    legal = related_entity_to_fact({
        "name": "HAWK-EYE INNOVATIONS LIMITED",
        "lei": "549300PBW7OURNSVGL39",
        "jurisdiction": "GB",
        "relationship": "ULTIMATE_ACCOUNTING_CHILD",
        "relationships": ["ULTIMATE_ACCOUNTING_CHILD"],
        "raw_relationship": "IS_ULTIMATELY_CONSOLIDATED_BY",
        "raw_relationships": ["IS_ULTIMATELY_CONSOLIDATED_BY"],
        "direction": "INBOUND",
        "entity_status": "ACTIVE",
        "registration_status": "ISSUED",
        "relationship_status": "ACTIVE",
        "source": "GLEIF",
        "corporate_confidence": "HIGH",
        "infrastructure_attribution_confidence": "UNKNOWN",
        "enrichment_state": "RESOLVED",
    })

    calls = []
    def candidate_fn(pivot, iteration):
        calls.append((pivot.fact_type, iteration))
        if pivot.fact_type != "LEGAL_ENTITY":
            return []
        return [build_candidate(
            entity(),
            "hawkeyeinnovations.com",
            [ev(EvidenceType.OFFICIAL_WEBSITE)],
        )]

    provider = DomainCandidateExpansionProvider(candidate_fn)
    result = run_expansion([legal], [provider], max_iterations=5)
    domains = [f for f in result.facts if f.fact_type == "DOMAIN"]
    assert len(domains) == 1
    assert domains[0].can_pivot()
    # The accepted domain returns to the frontier. candidate_fn sees it, but the
    # provider itself ignores DOMAIN because only corporate pivot types are accepted.
    assert result.converged
    assert result.stop_reason == "NO_NEW_TRUSTED_PIVOTS"


if __name__ == "__main__":
    tests = [
        test_auto_high_domain_becomes_recursive_pivot,
        test_review_domain_is_preserved_but_not_recursive,
        test_rejected_domain_is_preserved_and_blocked,
        test_high_corporate_confidence_cannot_promote_domain,
        test_provider_adds_domain_fact_but_only_auto_reenters_frontier,
    ]
    failed = 0
    for test in tests:
        try:
            test()
            print(f"PASS {test.__name__}")
        except Exception as exc:
            failed += 1
            print(f"FAIL {test.__name__}: {type(exc).__name__}: {exc}")
    print(f"\n{len(tests)-failed} passed / {failed} failed")
    raise SystemExit(1 if failed else 0)
