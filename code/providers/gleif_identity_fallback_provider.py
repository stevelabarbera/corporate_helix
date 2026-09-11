#!/usr/bin/env python3
"""
Corporation Helix -- GLEIF identity fallback provider.

Most subsidiaries stop filing under their own name with the SEC once fully
absorbed into an acquirer -- that's not a discovery-mechanism bug, it's how
SEC reporting actually works (their financials get consolidated into the
parent's reports instead). When EdgarMAExpansionProvider finds nothing for
a pivot, that is exactly the "reviewed candidate, data unknown/minimal"
state this provider exists to catch: GLEIF's relationship data does not
require independent SEC-filer status, so a company that has gone quiet on
EDGAR can often still be placed in a current ownership structure via its
LEI.

This deliberately does not try to replicate EDGAR's event history (who
acquired whom, when) -- it only surfaces GLEIF's answer to "who owns this
entity now," via the already-built, already-tested root_entity_resolver.
It only fires on AUTO_RESOLVED name matches; a REVIEW_REQUIRED or NO_MATCH
result produces no fact, consistent with the project's standing rule that
false-positive attribution is worse than leaving something unresolved.
"""
from __future__ import annotations

from typing import Callable, Iterable

from iterative_expansion import HelixFact
from expansion_bridges import LEGAL_ENTITY_FACT_TYPE, ROOT_FACT_TYPE


def _default_resolve(name: str, lei_index: str, rr_index: str):
    from root_entity_resolver import resolve_company_root
    return resolve_company_root(name, lei_index, rr_index)


class GleifIdentityFallbackProvider:
    """
    HelixFact provider: for any COMPANY/LEGAL_ENTITY pivot, resolves its name
    against the GLEIF LEI index. If it AUTO_RESOLVES to a root whose LEI the
    pivot doesn't already carry, emits a fact for that resolved identity --
    typically the pivot's current parent, or a confirmation of the pivot's
    own LEI if it's the root itself.

    Only fires when the pivot has no LEI recorded yet (pivot.identifier is
    falsy) -- once an entity's LEI is known, re-resolving it by name on
    every iteration would be redundant work, not new information.
    """

    def __init__(
        self,
        lei_index: str = "data/processed/gleif_lei.sqlite",
        rr_index: str = "data/processed/gleif_rr.sqlite",
        *,
        resolve_fn: Callable[[str, str, str], object] | None = None,
        accepted_pivot_types: Iterable[str] = (ROOT_FACT_TYPE, LEGAL_ENTITY_FACT_TYPE),
    ) -> None:
        self.lei_index = lei_index
        self.rr_index = rr_index
        self.resolve_fn = resolve_fn or _default_resolve
        self.accepted_pivot_types = {str(t).strip().upper() for t in accepted_pivot_types}

    def __call__(self, pivot: HelixFact, iteration: int) -> Iterable[HelixFact]:
        if pivot.fact_type.strip().upper() not in self.accepted_pivot_types:
            return []
        if pivot.identifier:
            return []  # already has an LEI; nothing new to resolve here

        result = self.resolve_fn(pivot.value, self.lei_index, self.rr_index)
        if result.status != "AUTO_RESOLVED" or not result.root:
            return []

        root = result.root
        return [HelixFact(
            fact_type=LEGAL_ENTITY_FACT_TYPE,
            value=root.legal_name or pivot.value,
            identifier=root.lei,
            source="GLEIF_IDENTITY_FALLBACK",
            confidence=result.confidence or "MEDIUM",
            status="ACCEPTED",
            pivot_eligible=True,
            evidence=[{
                "type": "GLEIF_NAME_RESOLUTION",
                "queried_as": pivot.value,
                "resolution_reason": result.reason,
            }],
            metadata={
                "discovered_via": "GLEIF_IDENTITY_FALLBACK",
                "discovered_from": pivot.value,
                "jurisdiction": root.jurisdiction,
                "entity_status": root.entity_status,
            },
        )]
