#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "code"))

from expansion_bridges import GleifCompanyExpansionProvider, company_seed, related_entity_to_fact
from iterative_expansion import run_expansion


class FakeConn:
    def close(self):
        pass


def sample_entity(name="HAWK-EYE INNOVATIONS LIMITED", lei="549300PBW7OURNSVGL39"):
    return {
        "name": name,
        "lei": lei,
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
    }


def test_seed_is_trusted_corporate_not_infrastructure():
    fact = company_seed("Sony", "529900R5WX9N2OI2N910")
    assert fact.can_pivot()
    assert fact.metadata["infrastructure_attribution_confidence"] == "UNKNOWN"


def test_resolved_high_gleif_entity_is_corporate_pivot():
    fact = related_entity_to_fact(sample_entity(), root_lei="ROOT")
    assert fact.fact_type == "LEGAL_ENTITY"
    assert fact.identifier == "549300PBW7OURNSVGL39"
    assert fact.status == "ACCEPTED"
    assert fact.confidence == "HIGH"
    assert fact.can_pivot()
    assert fact.metadata["infrastructure_attribution_confidence"] == "UNKNOWN"


def test_unresolved_entity_stays_review_and_cannot_pivot():
    row = sample_entity(name="UNKNOWN", lei="ABC")
    row["enrichment_state"] = "UNRESOLVED_LEVEL1"
    fact = related_entity_to_fact(row, root_lei="ROOT")
    assert fact.status == "REVIEW"
    assert fact.confidence == "UNKNOWN"
    assert not fact.can_pivot()


def test_provider_expands_only_company_root():
    calls = {"expand": 0}

    def connect_fn(path):
        return FakeConn()

    def lookup_fn(conn, lei):
        return {"lei": lei, "legal_name": "Sony Group Corporation"}

    def expand_fn(root, lei_db, rr_db):
        calls["expand"] += 1
        return [sample_entity()]

    provider = GleifCompanyExpansionProvider(
        "lei.sqlite", "rr.sqlite",
        lookup_fn=lookup_fn, expand_fn=expand_fn, connect_fn=connect_fn,
    )

    seed = company_seed("Sony", "529900R5WX9N2OI2N910")
    result = run_expansion([seed], [provider], max_iterations=5)

    legal = [f for f in result.facts if f.fact_type == "LEGAL_ENTITY"]
    assert len(legal) == 1
    assert legal[0].can_pivot()
    # Iteration 2 receives the LEGAL_ENTITY frontier, but this provider ignores it.
    assert calls["expand"] == 1
    assert result.converged
    assert result.stop_reason == "NO_NEW_TRUSTED_PIVOTS"


def test_provider_preserves_multiple_relationships():
    row = sample_entity()
    row["relationships"] = ["DIRECT_ACCOUNTING_CHILD", "ULTIMATE_ACCOUNTING_CHILD"]
    row["raw_relationships"] = ["IS_DIRECTLY_CONSOLIDATED_BY", "IS_ULTIMATELY_CONSOLIDATED_BY"]
    fact = related_entity_to_fact(row, root_lei="ROOT")
    assert fact.metadata["relationships"] == ["DIRECT_ACCOUNTING_CHILD", "ULTIMATE_ACCOUNTING_CHILD"]
    assert fact.evidence[0]["raw_relationships"] == [
        "IS_DIRECTLY_CONSOLIDATED_BY", "IS_ULTIMATELY_CONSOLIDATED_BY"
    ]


if __name__ == "__main__":
    tests = [
        test_seed_is_trusted_corporate_not_infrastructure,
        test_resolved_high_gleif_entity_is_corporate_pivot,
        test_unresolved_entity_stays_review_and_cannot_pivot,
        test_provider_expands_only_company_root,
        test_provider_preserves_multiple_relationships,
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
