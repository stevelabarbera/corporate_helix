#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CODE = ROOT / "code"
if str(CODE) not in sys.path:
    sys.path.insert(0, str(CODE))

from analysts.base import AnalystDecisionType
from analysts.llm_analyst import _normalize_response, validate_decisions, PROMPT_VERSION


def _validate(raw):
    return validate_decisions(raw, subject="Example Corp", subject_identifier="LEI1", model="test", iteration=2)


def test_suggestions_wrapper_is_accepted():
    d = _validate({"suggestions": [{"decision_type": "PROPOSE_DOMAIN", "value": "example.com"}]})
    assert len(d) == 1 and d[0].decision_type == AnalystDecisionType.PROPOSE_DOMAIN


def test_short_type_alias_is_conservative_proposal():
    d = _validate([{"type": "domain", "value": "example.com", "confidence": "high"}])
    assert len(d) == 1
    assert d[0].decision_type == AnalystDecisionType.PROPOSE_DOMAIN
    assert d[0].pivot_eligible is False


def test_domain_field_can_supply_value_but_not_trust():
    d = _validate([{"action": "PROPOSE_DOMAIN", "domain": "example.com", "confidence": "HIGH"}])
    assert len(d) == 1 and d[0].value == "example.com"
    assert d[0].pivot_eligible is False


def test_ownership_declaration_still_dropped():
    assert _validate([{"type": "DECLARE_OWNERSHIP", "value": "example.com"}]) == []


def test_prompt_version_bumped():
    d = _validate([{"type": "brand", "value": "Example"}])
    assert d[0].prompt_version == PROMPT_VERSION == "m43c-analyst-v2"


def main():
    tests = [
        test_suggestions_wrapper_is_accepted,
        test_short_type_alias_is_conservative_proposal,
        test_domain_field_can_supply_value_but_not_trust,
        test_ownership_declaration_still_dropped,
        test_prompt_version_bumped,
    ]
    failures = 0
    for t in tests:
        try:
            t(); print(f"PASS {t.__name__}")
        except Exception as exc:
            failures += 1; print(f"FAIL {t.__name__}: {type(exc).__name__}: {exc}")
    print(f"\n{len(tests)-failures} passed / {failures} failed")
    return 1 if failures else 0

if __name__ == "__main__":
    raise SystemExit(main())
