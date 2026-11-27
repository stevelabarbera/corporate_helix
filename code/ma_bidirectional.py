#!/usr/bin/env python3
"""Bounded GLEIF -> SEC M&A investigation; no autonomous graph expansion.

L2 accounting edges create research leads, not acquisitions. Only exact LEI-
identified counterparties with an SEC-filing identity can yield transaction
evidence. Every result is REVIEW-only and provenance-bearing.
"""
from __future__ import annotations

from typing import Callable, Any

from iterative_expansion import HelixFact
from providers.gleif_relationship_provider import EDGE_FACT_TYPE
from root_entity_resolver import normalize_name

TRANSACTION_TYPES = {
    "ACQUIRED", "AGREED_TO_ACQUIRE", "MERGED_WITH",
    "MERGER", "COMPLETED_ACQUISITION",
}


def _sec_pair_event(sec_fact: HelixFact, investigated: str, root: str) -> list[dict[str, Any]]:
    """SEC counterparty output must name our exact other legal entity.

    The provider extracts an event from a filing for 'investigated'. The
    counterparty (sec_fact.value) must be the known root company, otherwise
    it is not evidence about this L2 pair.
    """
    if normalize_name(sec_fact.value) != normalize_name(root):
        return []
    return [
        {
            "accession": ev.get("accession"),
            "filing_date": ev.get("filing_date"),
            "document_url": ev.get("document_url"),
            "event_type": ev.get("event_type"),
            "event_status": ev.get("status"),
            "extraction_rule": ev.get("extraction_rule"),
            "source_text": ev.get("source_text"),
        }
        for ev in sec_fact.evidence
        if ev.get("type") == "EDGAR_MA_EVENT"
        and ev.get("event_type") in TRANSACTION_TYPES
        and normalize_name(ev.get("pivot_name") or "") == normalize_name(investigated)
    ]


def investigate_l2_leads(
    *, seed: HelixFact, facts: list[HelixFact], edgar_provider: Callable,
    max_probes: int = 3,
) -> dict[str, Any]:
    """Probe SEC for a bounded set of new entities surfaced by L2 edges.

    Does not append parser output into the trusted expansion graph. Every
    candidate is reviewed independently. Successful SEC pair matches don't
    imply that GLEIF relationship effective date equals acquisition date.
    """
    max_probes = max(0, int(max_probes))
    edges = [x for x in facts if x.fact_type == EDGE_FACT_TYPE]
    # Prioritize entities consolidated by the seed (potential acquisition
    # targets), then earlier relationship starts; preserve stable record order.
    leads = {}
    for edge in edges:
        ev = next((e for e in edge.evidence
                   if e.get("type") == "GLEIF_L2_ACCOUNTING_RELATIONSHIP"), None)
        if not ev or not ev.get("period_valid"):
            continue
        anchor_lei = edge.metadata.get("identity_anchor_lei")
        child, parent = edge.metadata["child"], edge.metadata["parent"]
        if child["lei"] == anchor_lei:
            opposite = parent
            direction = "SEED_IS_CHILD"
        elif parent["lei"] == anchor_lei:
            opposite = child
            direction = "SEED_IS_PARENT"
        else:
            continue
        if not opposite.get("legal_name") or opposite["lei"] == anchor_lei:
            continue
        ident = opposite["lei"]
        lead = leads.setdefault(ident, {
            "related_lei": ident,
            "related_name": opposite["legal_name"],
            "direction": direction,
            "relationship_fact_keys": [],
            "relationship_dates": [],
            "registration_statuses": [],
            "eligible_by_current_snapshot": [],
            "decision": "NOT_PROBED",
            "sec_events": [],
        })
        if edge.value not in lead["relationship_fact_keys"]:
            lead["relationship_fact_keys"].append(edge.value)
        if ev.get("relationship_start"):
            lead["relationship_dates"].append(ev["relationship_start"])
        if ev.get("registration_status"):
            lead["registration_statuses"].append(ev["registration_status"])
        if "eligible_by_current_snapshot_as_of" in ev:
            lead["eligible_by_current_snapshot"].append(bool(ev["eligible_by_current_snapshot_as_of"]))

    # Deterministic research priority, not acquisition-date inference.
    ranked = sorted(leads.values(), key=lambda x: (
        0 if x["direction"] == "SEED_IS_PARENT" else 1,
        0 if any(x["eligible_by_current_snapshot"]) else 1,
        0 if "PUBLISHED" in x["registration_statuses"] else 1,
        -max((int(d[:4]) for d in x["relationship_dates"] if d[:4].isdigit()), default=0),
        x["related_name"].casefold(),
    ))
    for idx, lead in enumerate(ranked, 1):
        lead["research_priority"] = idx
        lead["priority_basis"] = "DIRECTION_CURRENT_ELIGIBILITY_REGISTRATION_RELATIONSHIP_RECENCY"
    attempted = ranked[:max_probes]
    for lead in attempted:
        probe = HelixFact(
            fact_type="LEGAL_ENTITY",
            value=lead["related_name"],
            identifier=None,  # LEI is not a SEC CIK.
            source="GLEIF_L2_RESEARCH_PROBE",
            confidence="MEDIUM",
            status="REVIEW",
            pivot_eligible=False,
            metadata={"identifiers": {"lei": lead["related_lei"]},
                      "research_only": True},
        )
        try:
            sec_facts = list(edgar_provider(probe, 0) or [])
        except Exception as exc:
            lead["decision"] = "SEC_PROBE_ERROR"
            lead["error"] = f"{type(exc).__name__}: {exc}"
            lead["sec_probe"] = dict(probe.metadata.get("sec_probe") or {})
            continue
        coverage = probe.metadata.get("sec_probe")
        lead["sec_probe"] = dict(coverage) if coverage else {
            "status": "UNKNOWN_PROVIDER_COVERAGE",
            "cik": None, "filings_retrieved": None, "sections_retrieved": None,
        }
        status = lead["sec_probe"]["status"]
        if status == "NO_SEC_IDENTITY":
            lead["decision"] = "NO_SEC_IDENTITY"
            continue
        if status == "NO_SEC_FILINGS":
            lead["decision"] = "NO_SEC_FILINGS_RETRIEVED"
            continue
        if status == "NO_SEC_SECTIONS":
            lead["decision"] = "NO_SEC_SECTIONS_RETRIEVED"
            continue
        matches = []
        for sec_fact in sec_facts:
            matches.extend(_sec_pair_event(
                sec_fact, lead["related_name"], seed.value,
            ))
        if matches:
            lead["decision"] = "SEC_TRANSACTION_CANDIDATE_FOUND_REVIEW"
            lead["sec_events"] = matches
        else:
            lead["decision"] = (
                "SEC_FILINGS_EXAMINED_NO_PAIR_EVENT"
                if status == "FILINGS_RETRIEVED"
                else "NO_SEC_PAIR_EVENT_FOUND_COVERAGE_UNKNOWN"
            )
    return {
        "leads_found": len(ranked),
        "leads_probed": len(attempted),
        "leads_deferred": max(0, len(ranked) - len(attempted)),
        "probe_limit": max_probes,
        "leads": ranked,
        "policy": {
            "gleif_l2_is_acquisition": False,
            "probe_results_pivot_eligible": False,
            "no_sec_result_excludes_acquisition": False,
        },
    }
