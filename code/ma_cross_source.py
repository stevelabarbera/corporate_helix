#!/usr/bin/env python3
"""Join EDGAR M&A candidate evidence and GLEIF L2 accounting edges.

No inferred acquisition from L2, no automatic recursion of a parser candidate,
and no ASM scope promotion. The same HelixFact graph contains both evidence
types; explicit links require verified exact L1 legal-name identity.
"""
from __future__ import annotations

from dataclasses import asdict
from typing import Any, Callable

from iterative_expansion import ExpansionResult, HelixFact, merge_fact, run_expansion
from providers.gleif_relationship_provider import (
    EDGE_FACT_TYPE, GleifRelationshipEvidenceProvider,
    typed_pivot_lei, unique_exact_lei,
)
from root_entity_resolver import normalize_name


def join_evidence(result: ExpansionResult,
                  relationship_provider: GleifRelationshipEvidenceProvider,
                  *, max_candidates: int = 100) -> dict[str, Any]:
    """Enrich EDGAR non-pivot leads and link typed evidence in the shared graph.

    Existing trusted recursive expansion is left intact. GLEIF relationship
    output stays REVIEW/nonpivot even when it aligns with an EDGAR event.
    """
    facts = {f.key(): f for f in result.facts}
    candidates = [
        f for f in result.facts
        if f.source == "EDGAR_MA" and f.fact_type == "LEGAL_ENTITY"
    ]
    selected = candidates[:max_candidates]
    errors = []
    for candidate in selected:
        try:
            for edge in relationship_provider(candidate, result.iterations_run + 1):
                if edge.key() in facts:
                    merge_fact(facts[edge.key()], edge)
                else:
                    facts[edge.key()] = edge
        except Exception as exc:
            errors.append({
                "candidate": candidate.value,
                "error": f"{type(exc).__name__}: {exc}",
            })

    # Link SEC event evidence only to the exact legal entity on an actual L2
    # row, never to a name-matched ancestor or unrelated corporate group.
    # A cross-source link remains a review-only evidence association.
    links = []
    for candidate in selected:
        key = normalize_name(candidate.value)
        lei = relationship_provider._identity_cache.get(key) or typed_pivot_lei(candidate)
        if not lei:
            continue
        for edge in facts.values():
            if edge.fact_type != EDGE_FACT_TYPE:
                continue
            child = edge.metadata["child"]
            parent = edge.metadata["parent"]
            if lei not in (child["lei"], parent["lei"]):
                continue
            # An exact LEI on its own can refer to either a parent or a child.
            # Keep role and event classification explicit, not conflated.
            match_role = "CHILD" if lei == child["lei"] else "PARENT"
            sec_refs = [{
                "accession": ev.get("accession"),
                "event_type": ev.get("event_type"),
                "event_status": ev.get("status"),
                "subject": ev.get("subject"),
                "object": ev.get("object"),
                "filing_date": ev.get("filing_date"),
            } for ev in candidate.evidence if ev.get("type") == "EDGAR_MA_EVENT"]
            if not sec_refs:
                continue
            linked = {
                "type": "SEC_GLEIF_CANDIDATE_ASSOCIATION",
                "counterparty": candidate.value,
                "counterparty_lei": lei,
                "counterparty_role_in_l2": match_role,
                "edgar_event_evidence": sec_refs,
                "relation_fact_key": edge.value,
                "decision": "REVIEW_ONLY_NOT_TRANSACTION_CORROBORATION",
            }
            if linked not in edge.evidence:
                edge.evidence.append(linked)
            links.append({
                "candidate": candidate.value,
                "candidate_lei": lei,
                "relationship": edge.value,
                "status": "REVIEW_ONLY",
            })
    result.facts = list(facts.values())
    return {
        "sources": ["SEC_EDGAR", "GLEIF_L1_L2"],
        "relationship_facts": sum(f.fact_type == EDGE_FACT_TYPE for f in result.facts),
        "edgar_candidates_seen": len(candidates),
        "edgar_candidates_checked": len(selected),
        "edgar_candidates_truncated": len(selected) < len(candidates),
        "links": links,
        "gleif_coverage": list(relationship_provider.coverage),
        "errors": errors,
        "policy": {
            "gleif_infers_acquisition": False,
            "auto_promote_gleif_l2": False,
            "auto_authorize_asm_scope": False,
        },
    }


def run_integrated(seed: HelixFact, edgar_provider: Callable,
                   gleif_provider: GleifRelationshipEvidenceProvider, *,
                   max_iterations: int = 10,
                   max_sec_candidates: int = 100):
    """Production-facing orchestration; SEC and L2 facts share one graph."""
    result = run_expansion([seed], [edgar_provider, gleif_provider],
                           max_iterations=max_iterations)
    integration = join_evidence(result, gleif_provider,
                                max_candidates=max_sec_candidates)
    return result, integration
