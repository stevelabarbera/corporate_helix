#!/usr/bin/env python3
"""
Corporation Helix -- EDGAR M&A discovery provider.

Trust-boundary note (2026-09-13)
--------------------------------
Parser inference is candidate-generation evidence, not identity-grade evidence.

Historically this provider converted every completed parser event directly
into ACCEPTED/HIGH/pivot_eligible=True. Because several extraction branches
use deliberate heuristics ("nearest prior org", "earliest org after clause"),
a parser mistake could therefore become a recursive graph pivot and expand
ASM scope.

The default is now conservative:
- completed parser events are emitted as REVIEW/MEDIUM;
- they are NOT pivot eligible;
- a separate explicit authorize_pivot_fn must approve a candidate before it
  may recurse.

Long-form note (2026-09-13)
---------------------------
The live default acquisition path now includes locator-selected 10-K regions
in addition to 8-K Item 1.01/2.01 sections. The locator only expands the text
examined by the existing production extractor; it does not weaken the trust
boundary or authorize recursion.
"""
from __future__ import annotations

import hashlib
from typing import Any, Callable, Iterable

from iterative_expansion import HelixFact
from expansion_bridges import LEGAL_ENTITY_FACT_TYPE, ROOT_FACT_TYPE
from parsers.edgar_ma_extractor import EdgarMAExtractor
from providers.edgar_resolver import identity_key


def _default_fetch_filings(pivot: HelixFact) -> dict[str, Any] | None:
    from providers.edgar_resolver import fetch_ma_filings, resolve_cik_by_name

    user_agent = "CorporationHelix research contact@example.com"
    cik = pivot.identifier if (pivot.identifier or "").isdigit() else None
    if not cik:
        cik = resolve_cik_by_name(pivot.value, user_agent)
    if not cik:
        return None
    return fetch_ma_filings(cik, user_agent)


def other_party(event: dict[str, Any], pivot_name: str) -> str | None:
    if event.get("subject") == "REGISTRANT_SELF_REFERENCE":
        return event.get("object")
    if event.get("object") == "REGISTRANT_SELF_REFERENCE":
        return event.get("subject")

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


AuthorizePivotFn = Callable[[dict[str, Any], HelixFact, dict[str, Any]], bool]


class EdgarMAExpansionProvider:
    """
    Emits evidence-backed M&A counterparty candidate facts.

    Default candidates remain REVIEW/MEDIUM and non-pivotable. An explicit
    authorize_pivot_fn can promote a specific event to ACCEPTED/HIGH when a
    separate deterministic/adjudication policy has enough evidence.
    """

    def __init__(
        self,
        *,
        fetch_filings_fn: Callable[[HelixFact], dict[str, Any] | None] | None = None,
        accepted_pivot_types: Iterable[str] = (ROOT_FACT_TYPE, LEGAL_ENTITY_FACT_TYPE),
        spacy_model: str = "en_core_web_sm",
        allow_degraded_parser: bool = False,
        authorize_pivot_fn: AuthorizePivotFn | None = None,
    ) -> None:
        self.fetch_filings_fn = fetch_filings_fn or _default_fetch_filings
        self.accepted_pivot_types = {str(t).strip().upper() for t in accepted_pivot_types}
        self.extractor = EdgarMAExtractor(
            spacy_model=spacy_model,
            allow_degraded=allow_degraded_parser,
        )
        self.authorize_pivot_fn = authorize_pivot_fn

    def _parse_filing_section(self, text: str, item: str | None) -> dict[str, Any]:
        return self.extractor.parse_section(text, item)

    def __call__(self, pivot: HelixFact, iteration: int) -> Iterable[HelixFact]:
        if pivot.fact_type.strip().upper() not in self.accepted_pivot_types:
            return []

        data = self.fetch_filings_fn(pivot)
        if not data or not data.get("filings"):
            return []

        seen: dict[str, HelixFact] = {}
        for filing in data["filings"]:
            for section in filing.get("sections", []):
                text = section["text"]
                parsed = self._parse_filing_section(text, section.get("item"))
                fused = parsed["fused"]
                ensemble = parsed["ensemble"]

                for event in parsed["completed_events"]:
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
                        "form": filing.get("form"),
                        "item": section.get("item"),
                        "primary_document": filing.get("primary_document"),
                        "document_url": filing.get("document_url"),
                        "event_type": event.get("event_type"),
                        "status": event.get("status"),
                        "subject": event.get("subject"),
                        "object": event.get("object"),
                        "pivot_name": pivot.value,
                        "extraction_rule": event.get("extraction_rule"),
                        "source_text": event.get("evidence"),
                        "section_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
                        "parser_ensemble": ensemble,
                        "parser_org_votes": fused.get("org_votes", {}),
                        "parser_aliases": fused.get("aliases", {}),
                        "locator_version": section.get("locator_version"),
                        "locator_region_number": section.get("region_number"),
                        "locator_start_char": section.get("start_char"),
                        "locator_end_char": section.get("end_char"),
                        "locator_terms": section.get("locator_terms"),
                        "locator_hits": section.get("locator_hits"),
                    }

                    authorized = False
                    if self.authorize_pivot_fn is not None:
                        authorized = bool(self.authorize_pivot_fn(event, pivot, evidence_entry))

                    if authorized:
                        fact_status = "ACCEPTED"
                        confidence = "HIGH"
                        pivot_eligible = True
                        trust_decision = "EXPLICIT_PIVOT_AUTHORIZATION"
                    else:
                        fact_status = "REVIEW"
                        confidence = "MEDIUM"
                        pivot_eligible = False
                        trust_decision = "PARSER_CANDIDATE_REQUIRES_ADJUDICATION"

                    evidence_entry["trust_decision"] = trust_decision

                    if key in seen:
                        seen[key].evidence.append(evidence_entry)
                        if authorized:
                            seen[key].status = "ACCEPTED"
                            seen[key].confidence = "HIGH"
                            seen[key].pivot_eligible = True
                        continue

                    seen[key] = HelixFact(
                        fact_type=LEGAL_ENTITY_FACT_TYPE,
                        value=name,
                        identifier=None,
                        source="EDGAR_MA",
                        confidence=confidence,
                        status=fact_status,
                        pivot_eligible=pivot_eligible,
                        evidence=[evidence_entry],
                        metadata={
                            "discovered_via": "EDGAR_MA_EXPANSION",
                            "discovered_from": pivot.value,
                            "trust_boundary": trust_decision,
                        },
                    )

        return list(seen.values())
