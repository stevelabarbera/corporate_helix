#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CODE = ROOT / "code"
if str(CODE) not in sys.path:
    sys.path.insert(0, str(CODE))

from domain_candidates import EvidenceType, candidates_from_observations
from expansion_bridges import SeededOfficialSiteDomainProvider
from iterative_expansion import HelixFact


def legal_fact(name="HAWK-EYE INNOVATIONS LIMITED", lei="549300PBW7OURNSVGL39"):
    return HelixFact(
        fact_type="LEGAL_ENTITY",
        value=name,
        identifier=lei,
        source="GLEIF",
        confidence="HIGH",
        status="ACCEPTED",
        pivot_eligible=True,
        metadata={
            "relationships": ["ULTIMATE_ACCOUNTING_CHILD"],
            "corporate_confidence": "HIGH",
            "infrastructure_attribution_confidence": "UNKNOWN",
            "jurisdiction": "GB",
        },
    )


def verified_observations(entities, seeds, *, verify_official=False, timeout=20):
    entity = entities[0]
    seed = seeds[0]
    return [
        {
            "entity_lei": entity.entity_lei,
            "entity_name": entity.entity_name,
            "domain": "hawkeyeinnovations.com",
            "provider": seed.get("provider", "TEST_SEARCH"),
            "evidence_type": EvidenceType.CANDIDATE_DISCOVERY.value,
            "reference": seed["url"],
            "observed_value": "Hawk-Eye",
            "supports_attribution": None,
        },
        {
            "entity_lei": entity.entity_lei,
            "entity_name": entity.entity_name,
            "domain": "hawkeyeinnovations.com",
            "provider": "OFFICIAL_SITE",
            "evidence_type": EvidenceType.OFFICIAL_WEBSITE.value,
            "reference": seed["url"],
            "observed_value": entity.entity_name,
            "supports_attribution": True,
            "raw": {"match_method": "normalized_exact_legal_name"},
        },
    ]


def discovery_only_observations(entities, seeds, *, verify_official=False, timeout=20):
    entity = entities[0]
    seed = seeds[0]
    return [{
        "entity_lei": entity.entity_lei,
        "entity_name": entity.entity_name,
        "domain": "hawkeyeinnovations.com",
        "provider": seed.get("provider", "TEST_SEARCH"),
        "evidence_type": EvidenceType.CANDIDATE_DISCOVERY.value,
        "reference": seed["url"],
        "observed_value": "Hawk-Eye",
        "supports_attribution": None,
    }]


def make_provider(observation_fn):
    return SeededOfficialSiteDomainProvider(
        [{
            "entity_lei": "549300PBW7OURNSVGL39",
            "entity_name": "HAWK-EYE INNOVATIONS LIMITED",
            "url": "https://www.hawkeyeinnovations.com/terms-of-service",
            "provider": "TEST_SEARCH",
        }],
        observation_fn=observation_fn,
        candidates_fn=candidates_from_observations,
    )


def test_matching_legal_entity_reaches_auto_high_domain_pivot():
    facts = list(make_provider(verified_observations)(legal_fact(), 2))
    assert len(facts) == 1
    fact = facts[0]
    assert fact.fact_type == "DOMAIN"
    assert fact.value == "hawkeyeinnovations.com"
    assert fact.status == "ACCEPTED"
    assert fact.confidence == "HIGH"
    assert fact.can_pivot()


def test_candidate_discovery_alone_stays_review_unknown():
    facts = list(make_provider(discovery_only_observations)(legal_fact(), 2))
    assert len(facts) == 1
    fact = facts[0]
    assert fact.status == "REVIEW"
    assert fact.confidence == "UNKNOWN"
    assert not fact.can_pivot()


def test_nonmatching_legal_entity_produces_nothing():
    facts = list(make_provider(verified_observations)(legal_fact("PULSE INNOVATIONS LTD.", "549300CJ08WKF0TLAQ08"), 2))
    assert facts == []


def test_company_root_cannot_consume_domain_seed():
    root = HelixFact(
        fact_type="COMPANY",
        value="Sony",
        identifier="529900R5WX9N2OI2N910",
        confidence="HIGH",
        status="ACCEPTED",
        pivot_eligible=True,
    )
    facts = list(make_provider(verified_observations)(root, 1))
    assert facts == []


def test_high_corporate_confidence_still_cannot_promote_discovery_only():
    fact = list(make_provider(discovery_only_observations)(legal_fact(), 2))[0]
    assert fact.metadata["corporate_confidence"] == "HIGH"
    assert fact.metadata["domain_disposition"] == "REVIEW"
    assert not fact.can_pivot()


TESTS = [
    test_matching_legal_entity_reaches_auto_high_domain_pivot,
    test_candidate_discovery_alone_stays_review_unknown,
    test_nonmatching_legal_entity_produces_nothing,
    test_company_root_cannot_consume_domain_seed,
    test_high_corporate_confidence_still_cannot_promote_discovery_only,
]


if __name__ == "__main__":
    failures = 0
    for test in TESTS:
        try:
            test()
            print(f"PASS {test.__name__}")
        except Exception as exc:
            failures += 1
            print(f"FAIL {test.__name__}: {type(exc).__name__}: {exc}")
    print()
    print(f"{len(TESTS) - failures} passed / {failures} failed")
    raise SystemExit(1 if failures else 0)
