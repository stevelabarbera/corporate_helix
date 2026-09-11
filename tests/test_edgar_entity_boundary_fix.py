#!/usr/bin/env python3
"""
Regression test for a real bug found via the Disney/Fox cold-run data
(CONTEXT.md M3.8.5 legal-text parser): the shared entity-name regex used
by RegexBackend and LegalRulesBackend could match an entire clause/sentence
instead of just the organization name, whenever the clause contained an
earlier capitalized word and no other corporate-suffix occurrence before
the real one. On real EDGAR text this produced organization names like
"Disney will make a cash payment to New Fox, Inc." instead of "New Fox,
Inc.", which then poisoned the alias map and (in that filing) suppressed
event detection entirely.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))

_spec = importlib.util.spec_from_file_location(
    "m385", Path(__file__).resolve().parents[1] / "code" / "benchmark_m385_merger_coref.py"
)
m385 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(m385)

# Real text pulled from data/raw/edgar_disney_fox_cold_m386.json
REAL_BAD_1 = (
    "Additionally, if the final estimate of such tax liabilities is lower than "
    "$8.5 billion, Disney will make a cash payment to New Fox, Inc. (\u201cNew Fox\u201d) "
    "reflecting the difference between such amount and $8.5 billion"
)
REAL_BAD_2 = (
    "On June 20, 2018, concurrently with the execution of the Amended and Restated "
    "Merger Agreement, Disney entered into an Amended and Restated Voting Agreement "
    "with Murdoch Family Trust and Cruden Financial Services LLC (collectively,"
)


def test_regex_backend_does_not_swallow_preceding_clause():
    backend = m385.RegexBackend()
    result = backend.parse(REAL_BAD_1)
    assert "New Fox, Inc." in result["orgs"], result["orgs"]
    assert not any(o.startswith("Disney will make") for o in result["orgs"]), result["orgs"]
    print("PASS test_regex_backend_does_not_swallow_preceding_clause")


def test_regex_backend_multi_word_connector_entity_still_matches():
    backend = m385.RegexBackend()
    result = backend.parse(REAL_BAD_2)
    assert "Murdoch Family Trust and Cruden Financial Services LLC" in result["orgs"], result["orgs"]
    assert not any(o.startswith("Voting Agreement with") for o in result["orgs"]), result["orgs"]
    print("PASS test_regex_backend_multi_word_connector_entity_still_matches")


def test_numeric_token_in_entity_name_still_matches():
    # "TWDC Holdco 613 Corp." -- a digit-led token mid-name must not break
    # the word chain.
    backend = m385.RegexBackend()
    result = backend.parse("The parties formed TWDC Holdco 613 Corp. for this purpose.")
    assert "TWDC Holdco 613 Corp." in result["orgs"], result["orgs"]
    print("PASS test_numeric_token_in_entity_name_still_matches")


def test_legal_rules_backend_same_fix_applies():
    # LegalRulesBackend shares the same ENT regex and must be fixed too --
    # this was originally duplicated code with the identical bug in both
    # classes.
    backend = m385.LegalRulesBackend()
    text = REAL_BAD_1 + ' (referred to herein as "New Fox")'
    result = backend.parse(text)
    assert not any(o.startswith("Disney will make") for o in result["orgs"]), result["orgs"]
    print("PASS test_legal_rules_backend_same_fix_applies")


def test_hyphenated_name_still_matches():
    backend = m385.RegexBackend()
    result = backend.parse("The merger with Twenty-First Century Fox, Inc. was completed.")
    assert "Twenty-First Century Fox, Inc." in result["orgs"], result["orgs"]
    print("PASS test_hyphenated_name_still_matches")


if __name__ == "__main__":
    suite = [
        test_regex_backend_does_not_swallow_preceding_clause,
        test_regex_backend_multi_word_connector_entity_still_matches,
        test_numeric_token_in_entity_name_still_matches,
        test_legal_rules_backend_same_fix_applies,
        test_hyphenated_name_still_matches,
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
