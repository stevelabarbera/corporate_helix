#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CODE = REPO / "code"
if str(CODE) not in sys.path:
    sys.path.insert(0, str(CODE))

from expansion_bridges import DiscoveringOfficialSiteDomainProvider
from iterative_expansion import HelixFact


def legal_entity():
    return HelixFact(
        fact_type="LEGAL_ENTITY",
        value="EXAMPLE LEGAL ENTITY LTD",
        identifier="LEI123",
        source="GLEIF",
        confidence="HIGH",
        status="ACCEPTED",
        pivot_eligible=True,
        metadata={
            "relationships": ["ULTIMATE_ACCOUNTING_CHILD"],
            "corporate_confidence": "HIGH",
            "jurisdiction": "GB",
        },
    )


def test_zero_knowledge_provider_searches_without_seed_input():
    calls = {"discover": 0, "observe": 0, "candidate": 0}

    def discover(entities, *, max_results_per_entity, timeout):
        calls["discover"] += 1
        return ([{
            "entity_lei": "LEI123",
            "entity_name": "EXAMPLE LEGAL ENTITY LTD",
            "url": "https://example.com/legal",
            "provider": "WEB_SEARCH",
        }], [])

    def observe(entities, seeds, *, verify_official, timeout):
        calls["observe"] += 1
        return [{"fake": "observation"}]

    class Candidate:
        candidate_domain = "example.com"
        entity_name = "EXAMPLE LEGAL ENTITY LTD"
        entity_lei = "LEI123"
        relationships = []
        jurisdiction = "GB"
        corporate_confidence = "HIGH"
        registrable_domain = "example.com"
        infrastructure_attribution_confidence = "HIGH"
        disposition = "AUTO"
        review_reason = None
        def to_dict(self):
            return {"evidence": [{"evidence_type": "OFFICIAL_WEBSITE"}]}

    def candidates(entities, observations):
        calls["candidate"] += 1
        return [Candidate()]

    provider = DiscoveringOfficialSiteDomainProvider(
        discovery_fn=discover,
        observation_fn=observe,
        candidates_fn=candidates,
    )
    facts = list(provider(legal_entity(), 2))

    assert len(facts) == 1
    assert facts[0].fact_type == "DOMAIN"
    assert facts[0].status == "ACCEPTED"
    assert facts[0].confidence == "HIGH"
    assert facts[0].can_pivot()
    assert calls == {"discover": 1, "observe": 1, "candidate": 1}
    print("PASS test_zero_knowledge_provider_searches_without_seed_input")


def test_zero_knowledge_provider_ignores_non_legal_entity():
    provider = DiscoveringOfficialSiteDomainProvider(
        discovery_fn=lambda *a, **k: (_ for _ in ()).throw(
            AssertionError("must not search")
        ),
        observation_fn=lambda *a, **k: [],
        candidates_fn=lambda *a, **k: [],
    )
    pivot = legal_entity()
    pivot.fact_type = "DOMAIN"
    assert list(provider(pivot, 1)) == []
    print("PASS test_zero_knowledge_provider_ignores_non_legal_entity")


def test_search_errors_are_preserved_not_promoted():
    def discover(entities, *, max_results_per_entity, timeout):
        return [], [{
            "entity_lei": "LEI123",
            "entity_name": "EXAMPLE LEGAL ENTITY LTD",
            "error": "TimeoutError: search timed out",
        }]

    provider = DiscoveringOfficialSiteDomainProvider(
        discovery_fn=discover,
        observation_fn=lambda *a, **k: [],
        candidates_fn=lambda *a, **k: [],
    )
    assert list(provider(legal_entity(), 1)) == []
    assert len(provider.search_errors) == 1
    print("PASS test_search_errors_are_preserved_not_promoted")


if __name__ == "__main__":
    tests = [
        test_zero_knowledge_provider_searches_without_seed_input,
        test_zero_knowledge_provider_ignores_non_legal_entity,
        test_search_errors_are_preserved_not_promoted,
    ]
    failed = 0
    for t in tests:
        try:
            t()
        except Exception as exc:
            failed += 1
            print(f"FAIL {t.__name__}: {exc}")
    print(f"{len(tests)-failed} passed / {failed} failed")
    raise SystemExit(1 if failed else 0)
