#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "code"))

from domain_candidates import (  # noqa: E402
    CorporateEntity,
    Disposition,
    InfrastructureConfidence,
    candidates_from_observations,
)
from providers.official_site import inspect_html  # noqa: E402


def _entity() -> CorporateEntity:
    return CorporateEntity(
        entity_name="Sony Interactive Entertainment Europe Limited",
        entity_lei="5493005M7S82SGBTH640",
        relationships=["DIRECT_ACCOUNTING_CHILD"],
        corporate_confidence="HIGH",
        jurisdiction="GB",
    )


def test_discovery_provenance_is_not_attribution():
    entity = _entity()
    obs = [{
        "entity_lei": entity.entity_lei,
        "domain": "playstation.com",
        "provider": "WEB_SEARCH",
        "evidence_type": "CANDIDATE_DISCOVERY",
        "reference": "https://www.playstation.com/en-ie/legal/",
        "supports_attribution": None,
    }]
    candidate = candidates_from_observations([entity], obs)[0]
    assert candidate.disposition is Disposition.REVIEW
    assert candidate.infrastructure_attribution_confidence is InfrastructureConfidence.UNKNOWN


def test_exact_legal_name_on_page_is_official_declaration():
    page = inspect_html(
        "https://www.playstation.com/en-ie/legal/",
        "<html><title>Legal</title><body>© 2026 Sony Interactive Entertainment Europe Limited (SIEE)</body></html>",
        "Sony Interactive Entertainment Europe Limited",
    )
    assert page.exact_legal_name_match is True
    assert page.matched_name == "Sony Interactive Entertainment Europe Limited"


def test_brand_only_page_is_not_legal_entity_declaration():
    page = inspect_html(
        "https://www.playstation.com/",
        "<html><body>PlayStation. Play Has No Limits.</body></html>",
        "Sony Interactive Entertainment Europe Limited",
    )
    assert page.exact_legal_name_match is False


def test_official_declaration_can_auto():
    entity = _entity()
    obs = [
        {
            "entity_lei": entity.entity_lei,
            "domain": "playstation.com",
            "provider": "WEB_SEARCH",
            "evidence_type": "CANDIDATE_DISCOVERY",
            "reference": "https://www.playstation.com/en-ie/legal/",
            "supports_attribution": None,
        },
        {
            "entity_lei": entity.entity_lei,
            "domain": "playstation.com",
            "provider": "OFFICIAL_SITE",
            "evidence_type": "OFFICIAL_WEBSITE",
            "reference": "https://www.playstation.com/en-ie/legal/",
            "observed_value": entity.entity_name,
            "supports_attribution": True,
        },
    ]
    candidate = candidates_from_observations([entity], obs)[0]
    assert candidate.disposition is Disposition.AUTO
    assert candidate.infrastructure_attribution_confidence is InfrastructureConfidence.HIGH


def main() -> int:
    tests = [
        test_discovery_provenance_is_not_attribution,
        test_exact_legal_name_on_page_is_official_declaration,
        test_brand_only_page_is_not_legal_entity_declaration,
        test_official_declaration_can_auto,
    ]
    passed = 0
    for test in tests:
        try:
            test()
            print(f"PASS {test.__name__}")
            passed += 1
        except Exception as exc:
            print(f"FAIL {test.__name__}: {exc}")
    print(f"\n{passed} passed / {len(tests) - passed} failed")
    return 0 if passed == len(tests) else 1


if __name__ == "__main__":
    raise SystemExit(main())
