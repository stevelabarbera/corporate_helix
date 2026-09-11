#!/usr/bin/env python3
"""
Corporation Helix -- EDGAR M&A recursive discovery provider.

The goal (as scoped): given a company, find every merger/acquisition it has
been part of, and for every OTHER company that surfaces, recurse -- find
every merger/acquisition THAT company has been part of, and so on, until
nothing new turns up.

This plugs into the same iterative_expansion.run_expansion() engine already
used for GLEIF-based expansion (see expansion_bridges.py) rather than being
a second bespoke recursion loop: HelixFact objects this provider emits get
fed straight back into run_expansion()'s frontier, so they're eligible for
further EDGAR recursion AND for every other registered provider (a GLEIF
identity lookup, domain attribution, etc.) without any extra wiring.

Why recursion naturally terminates in practice: most subsidiaries stop
filing under their own name once fully absorbed into an acquirer (their
financials get consolidated into the parent's reports). That's not a bug in
this provider -- it's the real shape of SEC reporting. When EDGAR has
nothing left to say about a company, that is exactly the "reviewed
candidate, data unknown/minimal" state the GLEIF fallback provider
(gleif_identity_fallback_provider.py) is meant to catch: GLEIF's
relationship data does not require independent SEC-filer status, so it can
often keep the ownership thread going past the point where EDGAR goes
quiet.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any, Callable, Iterable

from iterative_expansion import HelixFact
from expansion_bridges import LEGAL_ENTITY_FACT_TYPE, ROOT_FACT_TYPE
from providers.edgar_resolver import identity_key

_PARSER_PATH = Path(__file__).resolve().parents[1] / "benchmark_m385_merger_coref.py"


def _load_parser_module():
    spec = importlib.util.spec_from_file_location("m385_parser", _PARSER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _default_fetch_filings(pivot: HelixFact) -> dict[str, Any] | None:
    """
    Live default: resolve the pivot's name to a CIK and fetch its 8-K M&A
    filings from SEC EDGAR. Requires network access to sec.gov, which this
    sandbox does not have -- verified offline against fixture data instead;
    inject fetch_filings_fn with a fixture-backed function for testing, or
    run this default somewhere with real network access before trusting it.
    """
    from providers.edgar_resolver import fetch_8k_ma_filings, resolve_cik_by_name

    user_agent = "CorporationHelix research contact@example.com"
    cik = pivot.identifier if (pivot.identifier or "").isdigit() else None
    if not cik:
        cik = resolve_cik_by_name(pivot.value, user_agent)
    if not cik:
        return None
    return fetch_8k_ma_filings(cik, user_agent)


def other_party(event: dict[str, Any], pivot_name: str) -> str | None:
    """
    Given a COMPLETED merger/acquisition event and the pivot's own name,
    return whichever side of the event is NOT the pivot -- the newly
    discovered company. Returns None if neither side matches the pivot
    (ambiguous; skipped rather than guessed) or if both sides do (a
    self-referential/garbled extraction).
    """
    pivot_key = identity_key(pivot_name)
    subject_key = identity_key(event.get("subject") or "")
    object_key = identity_key(event.get("object") or "")

    subject_is_pivot = subject_key == pivot_key
    object_is_pivot = object_key == pivot_key

    if subject_is_pivot and not object_is_pivot:
        return event.get("object")
    if object_is_pivot and not subject_is_pivot:
        return event.get("subject")
    return None


class EdgarMAExpansionProvider:
    """
    HelixFact provider: for a COMPANY or LEGAL_ENTITY pivot, fetches its 8-K
    Item 1.01/2.01 filings, parses them with the (entity-boundary-fixed)
    M3.8.5 ensemble, and emits a LEGAL_ENTITY fact for every OTHER company
    involved in a COMPLETED merger/acquisition event. Those facts are
    pivot-eligible, so they re-enter run_expansion()'s frontier and get the
    same treatment on the next iteration.
    """

    def __init__(
        self,
        *,
        fetch_filings_fn: Callable[[HelixFact], dict[str, Any] | None] | None = None,
        accepted_pivot_types: Iterable[str] = (ROOT_FACT_TYPE, LEGAL_ENTITY_FACT_TYPE),
    ) -> None:
        self.fetch_filings_fn = fetch_filings_fn or _default_fetch_filings
        self.accepted_pivot_types = {str(t).strip().upper() for t in accepted_pivot_types}
        self._parser = _load_parser_module()

    def _parse_filing_section(self, text: str, item: str | None) -> tuple[dict, dict]:
        backends = [self._parser.RegexBackend(), self._parser.LegalRulesBackend()]
        outputs = {b.name: b.parse(text) for b in backends}
        fused = self._parser.fuse(outputs, {"regex": 0.5, "legal_rules": 1.25}, 1.0)
        events = self._parser.infer_events(text, fused["aliases"], fused["orgs"], item)
        return fused, self._parser.completed_only(events)

    def __call__(self, pivot: HelixFact, iteration: int) -> Iterable[HelixFact]:
        if pivot.fact_type.strip().upper() not in self.accepted_pivot_types:
            return []

        data = self.fetch_filings_fn(pivot)
        if not data or not data.get("filings"):
            # EDGAR has nothing for this pivot -- not an error. This is the
            # exact "reviewed candidate, minimal/unknown data" state the
            # GLEIF fallback provider is meant to pick up.
            return []

        seen: dict[str, HelixFact] = {}
        for filing in data["filings"]:
            for section in filing.get("sections", []):
                _, completed_events = self._parse_filing_section(section["text"], section.get("item"))
                for event in completed_events:
                    name = other_party(event, pivot.value)
                    if not name:
                        continue
                    key = identity_key(name)
                    if not key:
                        continue

                    evidence_entry = {
                        "type": "EDGAR_MA_EVENT",
                        "accession": filing.get("accession"),
                        "filing_date": filing.get("filing_date"),
                        "item": section.get("item"),
                        "event_type": event.get("event_type"),
                        "status": event.get("status"),
                        "pivot_name": pivot.value,
                    }

                    if key in seen:
                        seen[key].evidence.append(evidence_entry)
                        continue

                    seen[key] = HelixFact(
                        fact_type=LEGAL_ENTITY_FACT_TYPE,
                        value=name,
                        identifier=None,
                        source="EDGAR_MA",
                        confidence="HIGH",
                        status="ACCEPTED",
                        pivot_eligible=True,
                        evidence=[evidence_entry],
                        metadata={
                            "discovered_via": "EDGAR_MA_EXPANSION",
                            "discovered_from": pivot.value,
                        },
                    )

        return list(seen.values())
