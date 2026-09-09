#!/usr/bin/env python3
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CODE = ROOT / "code"
if str(CODE) not in sys.path:
    sys.path.insert(0, str(CODE))

from analysts.base import AnalystDecisionType
from analysts.llm_analyst import _extract_json, validate_decisions


def test_proposed_domain_can_never_pivot():
    decisions = validate_decisions(
        [{"decision_type": "PROPOSE_DOMAIN", "value": "example.com", "confidence": "HIGH", "reason": "name match"}],
        subject="Example Corporation",
        subject_identifier="LEI1",
        model="test",
        iteration=2,
    )
    assert len(decisions) == 1
    assert decisions[0].decision_type == AnalystDecisionType.PROPOSE_DOMAIN
    assert decisions[0].confidence == "HIGH"
    assert decisions[0].pivot_eligible is False
    assert decisions[0].metadata["requires_deterministic_corroboration"] is True


def test_invalid_decision_type_is_dropped():
    decisions = validate_decisions(
        [{"decision_type": "DECLARE_OWNERSHIP", "value": "example.com", "confidence": "HIGH"}],
        subject="Example Corporation",
        subject_identifier="LEI1",
        model="test",
        iteration=2,
    )
    assert decisions == []


def test_missing_value_is_dropped_except_abstain():
    decisions = validate_decisions(
        [
            {"decision_type": "PROPOSE_DOMAIN", "value": ""},
            {"decision_type": "ABSTAIN", "value": "", "reason": "insufficient evidence"},
        ],
        subject="Example Corporation",
        subject_identifier=None,
        model="test",
        iteration=2,
    )
    assert len(decisions) == 1
    assert decisions[0].decision_type == AnalystDecisionType.ABSTAIN


def test_confidence_is_bounded():
    decisions = validate_decisions(
        [{"decision_type": "PROPOSE_ALIAS", "value": "Example", "confidence": "CERTAIN"}],
        subject="Example Corporation",
        subject_identifier=None,
        model="test",
        iteration=2,
    )
    assert decisions[0].confidence == "UNKNOWN"


def test_json_extraction_accepts_fenced_or_wrapped_text():
    payload = _extract_json('prefix {"decisions":[{"decision_type":"ABSTAIN","value":""}]} suffix')
    assert payload["decisions"][0]["decision_type"] == "ABSTAIN"


def main():
    tests = [
        test_proposed_domain_can_never_pivot,
        test_invalid_decision_type_is_dropped,
        test_missing_value_is_dropped_except_abstain,
        test_confidence_is_bounded,
        test_json_extraction_accepts_fenced_or_wrapped_text,
    ]
    failures = 0
    for test in tests:
        try:
            test()
            print(f"PASS {test.__name__}")
        except Exception as exc:
            failures += 1
            print(f"FAIL {test.__name__}: {type(exc).__name__}: {exc}")
    print(f"\n{len(tests)-failures} passed / {failures} failed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
