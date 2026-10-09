from __future__ import annotations
from typing import Any

from models import Evidence, EntityCandidate, ProviderResult, RelationshipAssertion
from parsers.state_filing_extractor import extract_certificate_of_merger


class StateFilingProvider:
    """
    Wraps a parsed Certificate of Merger into the same ProviderResult /
    RelationshipAssertion / Evidence shape GleifRelationshipRecordAdapter
    emits, so a future fusion layer can consume EDGAR, GLEIF, and state
    filings uniformly without a provider-specific special case.

    Never fetches. Takes text already in hand -- a paste, an upload, an
    8-K exhibit someone already retrieved -- same boundary as
    ingest_supplied_evidence.py.
    """

    name = "state_filing"

    def from_text(
        self,
        text: str,
        *,
        jurisdiction: str = "Delaware",
        source_document_id: str | None = None,
        source_url: str | None = None,
    ) -> ProviderResult | None:
        parsed = extract_certificate_of_merger(text, jurisdiction=jurisdiction)
        if parsed is None:
            return None
        return self.from_parsed(parsed, source_document_id=source_document_id, source_url=source_url)

    def from_parsed(
        self,
        parsed: dict[str, Any],
        *,
        source_document_id: str | None = None,
        source_url: str | None = None,
    ) -> ProviderResult:
        surviving = parsed.get("surviving_entity")
        merging = parsed.get("merging_entity")
        jurisdictions = parsed.get("constituent_jurisdictions") or {}

        result = ProviderResult(
            provider=self.name,
            query=merging or surviving or "",
            resolved_name=surviving,
            metadata={
                "document_type": parsed.get("document_type"),
                "dgcl_section": parsed.get("dgcl_section"),
                "filing_jurisdiction": parsed.get("jurisdiction"),
                # The whole value proposition of this source is that it can
                # predate the matching 8-K by weeks -- make that explicit
                # on the result rather than leaving it implicit in "where
                # this data came from", so a fusion/ranking layer can treat
                # it as an early signal rather than just another relationship
                # record of unspecified recency.
                "signal_precedence": "pre_disclosure",
            },
        )

        if surviving:
            result.entities.append(EntityCandidate(
                provider=self.name,
                provider_entity_id=None,
                legal_name=surviving,
                jurisdiction=jurisdictions.get(surviving, parsed.get("jurisdiction")),
            ))
        if merging:
            result.entities.append(EntityCandidate(
                provider=self.name,
                provider_entity_id=None,
                legal_name=merging,
                jurisdiction=jurisdictions.get(merging, parsed.get("jurisdiction")),
            ))

        # effective_date is the legal effective date when a filing stamp or
        # explicit effective-time clause was present; otherwise None rather
        # than silently falling back to executed_date -- see the comment in
        # state_filing_extractor.py on why those two dates aren't
        # interchangeable. source_date carries whichever is actually known.
        source_date = parsed.get("effective_date") or parsed.get("executed_date")

        evidence = Evidence(
            provider=self.name,
            evidence_type="state_certificate_of_merger",
            source_url=source_url,
            source_document_id=source_document_id,
            source_date=source_date,
            extraction_method="state_filing_extractor",
            coverage="certificate_of_merger_text",
            raw_record=parsed,
            attributes={
                "dgcl_section": parsed.get("dgcl_section"),
                "effective_basis": parsed.get("effective_basis"),
                "executed_date": parsed.get("executed_date"),
            },
        )

        if surviving and merging:
            result.relationships.append(RelationshipAssertion(
                provider=self.name,
                subject_name=merging,
                # Reuses EDGAR's own MERGED_INTO predicate deliberately --
                # same real-world relationship (non-surviving entity merges
                # into surviving entity), same vocabulary, different source
                # document, so a fusion layer never has to reconcile two
                # different predicate names for one concept.
                predicate="MERGED_INTO",
                object_name=surviving,
                jurisdiction=parsed.get("jurisdiction"),
                relationship_status="COMPLETED" if parsed.get("effective_basis") else "FILED",
                evidence=[evidence],
                attributes={
                    "corporate_relationship_confidence": "high",
                    "infrastructure_attribution_confidence": "unknown",
                    "signal_precedence": "pre_disclosure",
                },
            ))
        else:
            result.warnings.append(
                "Could not resolve both surviving and merging entity names; "
                f"surviving={surviving!r}, merging={merging!r}. "
                "No relationship emitted."
            )

        return result
