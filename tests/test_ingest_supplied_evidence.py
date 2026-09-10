#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))

from domain_candidates import CorporateEntity, Disposition, DomainCandidate, InfrastructureConfidence, flag_shared_domain_conflicts
from ingest_supplied_evidence import build_observation_dicts


def _auto_candidate(name, lei, domain):
    return DomainCandidate(
        entity_name=name, entity_lei=lei, relationships=[], candidate_domain=domain,
        registrable_domain=domain, corporate_confidence="UNKNOWN",
        infrastructure_attribution_confidence=InfrastructureConfidence.HIGH,
        evidence=[], disposition=Disposition.AUTO, review_reason=None,
    )


def test_candidate_level_conflict_downgrades_both():
    candidates = [
        _auto_candidate("NTT DOCOMO BUSINESS", "LEI-A", "www.nttdata.com"),
        _auto_candidate("NTT FINANCE", "LEI-B", "www.nttdata.com"),
    ]
    result = flag_shared_domain_conflicts(candidates)
    assert all(c.disposition is Disposition.REVIEW for c in result)
    assert all(c.review_reason for c in result)
    print("PASS test_candidate_level_conflict_downgrades_both")


def test_candidate_level_single_claimant_unaffected():
    candidates = [_auto_candidate("Example Research Inc.", "LEI-A", "research.example")]
    result = flag_shared_domain_conflicts(candidates)
    assert result[0].disposition is Disposition.AUTO
    print("PASS test_candidate_level_single_claimant_unaffected")


def test_end_to_end_supplied_evidence_reproduces_ntt_conflict():
    # Full path: raw supplied observations -> bridge -> candidates_from_observations
    # -> shared-domain guard, using the exact real-world shape (two analysts/
    # tools independently tagging one shared portal to two different entities).
    from domain_candidates import candidates_from_observations

    entities = [
        CorporateEntity(entity_name="NTT DOCOMO BUSINESS", entity_lei="LEI-A"),
        CorporateEntity(entity_name="NTT FINANCE", entity_lei="LEI-B"),
    ]
    subjects = [
        {"entity_lei": "LEI-A", "domain": "www.nttdata.com", "observations": [
            {"capability": "CUSTOMER_ASSERTION", "provider": "analyst-a", "availability": "PROVIDED", "supports_attribution": True},
        ]},
        {"entity_lei": "LEI-B", "domain": "www.nttdata.com", "observations": [
            {"capability": "CUSTOMER_ASSERTION", "provider": "analyst-b", "availability": "PROVIDED", "supports_attribution": True},
        ]},
    ]
    observations = build_observation_dicts(subjects)
    candidates = candidates_from_observations(entities, observations)
    assert all(c.disposition is Disposition.REVIEW for c in candidates)
    print("PASS test_end_to_end_supplied_evidence_reproduces_ntt_conflict")


if __name__ == "__main__":
    suite = [
        test_candidate_level_conflict_downgrades_both,
        test_candidate_level_single_claimant_unaffected,
        test_end_to_end_supplied_evidence_reproduces_ntt_conflict,
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
