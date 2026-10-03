#!/usr/bin/env python3
"""
Regression test for M4.3C's domain-bridge CLI wiring.

Bug found 2026-09-29: run_iterative_company.py's documented
"Live Sony recursive-expansion checkpoint" (3 iterations: 15 legal
entities -> 2 domains -> 0, Converged=True) was not reproducible with the
checked-in script. The CLI only ever instantiated
GleifCompanyExpansionProvider -- there was no --domain-candidates argument
and nothing ever constructed a DomainCandidateExpansionProvider, even
though that class exists and is correctly implemented in
expansion_bridges.py.

Root cause, found via `git log -p`: a later commit (f9dcd9a, "Ran through
NTT as our new data identified a few bugs and new features", applied via
`git apply` from a patch whose own README describes it as wiring
root_entity_resolver into helix_company.py -- an entirely different
feature) also substantially rewrote expansion_bridges.py in the same
pass, and run_iterative_company.py's --domain-candidates flag and its
provider wiring were silently dropped as a side effect. No test existed
to catch this -- the "COMPLETE / LIVE VALIDATED" status in
CORPORATION_HELIX_CONTEXT.md was a one-time manual run, documented as
prose, never re-run after later commits touched the same files.

A second, smaller gap surfaced while restoring this: the original wiring
called `DomainCandidateExpansionProvider.from_json(...)`, but that
classmethod never existed on the CURRENT DomainCandidateExpansionProvider
(which takes a `candidate_fn` callable, not a file path) -- domain_candidates.py's
write_json() had no reverse (load_candidates()) at all, so a straight
revert of the old diff would not have actually worked either. This test
exercises the real fix: domain_candidates.load_candidates() as the read
side of write_json(), plus the corrected CLI wiring in
run_iterative_company.py, against the real saved Sony validation data
(data/processed/sony_official_site_candidates.json) rather than synthetic
placeholders.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))

from domain_candidates import load_candidates
from expansion_bridges import DomainCandidateExpansionProvider

SONY_CANDIDATES_FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "data/processed/sony_official_site_candidates.json"
)

PLAYSTATION_LEI = "5493005M7S82SGBTH640"
HAWKEYE_LEI = "549300PBW7OURNSVGL39"


class _FakePivot:
    def __init__(self, identifier: str, fact_type: str = "LEGAL_ENTITY"):
        self.identifier = identifier
        self.fact_type = fact_type


def test_load_candidates_round_trips_real_saved_sony_data():
    candidates = load_candidates(SONY_CANDIDATES_FIXTURE)
    leis = {c.entity_lei for c in candidates}
    assert PLAYSTATION_LEI in leis
    assert HAWKEYE_LEI in leis
    assert len(candidates) == 2


def test_domain_candidate_provider_emits_accepted_high_pivot_eligible_fact():
    # Matches the documented M4.3B->M4.3C mapping rule exactly:
    # AUTO + HIGH -> DOMAIN / ACCEPTED / HIGH / pivot eligible.
    candidates = load_candidates(SONY_CANDIDATES_FIXTURE)
    by_lei: dict[str, list] = {}
    for c in candidates:
        by_lei.setdefault(c.entity_lei, []).append(c)

    provider = DomainCandidateExpansionProvider(
        lambda pivot, iteration: by_lei.get(pivot.identifier, [])
    )

    facts = provider(_FakePivot(PLAYSTATION_LEI), 1)
    assert len(facts) == 1
    fact = facts[0]
    assert fact.fact_type == "DOMAIN"
    assert fact.value == "www.playstation.com"
    assert fact.status == "ACCEPTED"
    assert fact.confidence == "HIGH"
    assert fact.pivot_eligible is True


def test_domain_candidate_provider_returns_nothing_for_unrelated_pivot():
    candidates = load_candidates(SONY_CANDIDATES_FIXTURE)
    by_lei: dict[str, list] = {}
    for c in candidates:
        by_lei.setdefault(c.entity_lei, []).append(c)

    provider = DomainCandidateExpansionProvider(
        lambda pivot, iteration: by_lei.get(pivot.identifier, [])
    )

    facts = provider(_FakePivot("NOT-A-REAL-LEI-000000"), 1)
    assert facts == []


def test_run_iterative_company_cli_declares_domain_candidates_flag():
    # Regression guard for the actual CLI wiring, not just the library
    # functions: if --domain-candidates disappears from argparse again,
    # this fails immediately rather than silently losing the feature.
    import subprocess

    script = Path(__file__).resolve().parents[1] / "code" / "run_iterative_company.py"
    result = subprocess.run(
        [sys.executable, str(script), "--help"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert "--domain-candidates" in result.stdout
