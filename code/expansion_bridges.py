from __future__ import annotations

from typing import Any, Callable, Iterable

from iterative_expansion import HelixFact


ROOT_FACT_TYPE = "COMPANY"
LEGAL_ENTITY_FACT_TYPE = "LEGAL_ENTITY"


def company_seed(name: str, lei: str, *, source: str = "OPERATOR") -> HelixFact:
    """Create the trusted corporate root used to start a GLEIF expansion.

    This is a corporate query/root assertion only. It says nothing about
    infrastructure ownership.
    """
    return HelixFact(
        fact_type=ROOT_FACT_TYPE,
        value=name,
        identifier=lei,
        source=source,
        confidence="HIGH",
        status="ACCEPTED",
        pivot_eligible=True,
        evidence=[
            {
                "type": "ROOT_SEED",
                "source": source,
                "name": name,
                "lei": lei,
            }
        ],
        metadata={
            "corporate_scope": True,
            "infrastructure_attribution_confidence": "UNKNOWN",
        },
    )


def related_entity_to_fact(entity: dict[str, Any], *, root_lei: str | None = None) -> HelixFact:
    """Convert one evaluated helix_company related entity into a HelixFact.

    GLEIF corporate confidence is preserved as corporate evidence only.
    It must never promote infrastructure attribution.
    """
    lei = str(entity.get("lei") or "").strip()
    name = str(entity.get("name") or lei).strip()
    resolved = entity.get("enrichment_state") == "RESOLVED"
    corporate_confidence = str(entity.get("corporate_confidence") or "UNKNOWN").upper()

    accepted = resolved and corporate_confidence == "HIGH" and bool(lei)

    evidence = [{
        "type": "GLEIF_RELATIONSHIP",
        "source": entity.get("source") or "GLEIF",
        "root_lei": root_lei,
        "related_lei": lei or None,
        "relationships": list(entity.get("relationships") or ([entity.get("relationship")] if entity.get("relationship") else [])),
        "raw_relationships": list(entity.get("raw_relationships") or ([entity.get("raw_relationship")] if entity.get("raw_relationship") else [])),
        "relationship_status": entity.get("relationship_status"),
        "relationship_start": entity.get("relationship_start"),
        "relationship_end": entity.get("relationship_end"),
        "accounting_start": entity.get("accounting_start"),
        "accounting_end": entity.get("accounting_end"),
        "validation_sources": entity.get("validation_sources"),
        "validation_documents": entity.get("validation_documents"),
        "validation_reference": entity.get("validation_reference"),
    }]

    return HelixFact(
        fact_type=LEGAL_ENTITY_FACT_TYPE,
        value=name,
        identifier=lei or None,
        source=entity.get("source") or "GLEIF",
        confidence="HIGH" if accepted else "UNKNOWN",
        status="ACCEPTED" if accepted else "REVIEW",
        pivot_eligible=accepted,
        evidence=evidence,
        metadata={
            "jurisdiction": entity.get("jurisdiction"),
            "entity_status": entity.get("entity_status"),
            "registration_status": entity.get("registration_status"),
            "direction": entity.get("direction"),
            "relationships": list(entity.get("relationships") or []),
            "raw_relationships": list(entity.get("raw_relationships") or []),
            "corporate_confidence": corporate_confidence,
            "infrastructure_attribution_confidence": entity.get(
                "infrastructure_attribution_confidence", "UNKNOWN"
            ),
            "enrichment_state": entity.get("enrichment_state"),
            "root_lei": root_lei,
        },
    )


class GleifCompanyExpansionProvider:
    """Bridge existing helix_company GLEIF expansion into M4.3C.

    First vertical slice intentionally reacts only to COMPANY root facts.
    The 15 resulting Sony LEGAL_ENTITY facts become eligible frontier facts,
    but this provider will not recursively walk them again. Other providers
    (domain discovery, analyst hypotheses, etc.) can consume those pivots.
    """

    def __init__(
        self,
        lei_db: str = "data/processed/gleif_lei.sqlite",
        rr_db: str = "data/processed/gleif_rr.sqlite",
        *,
        lookup_fn: Callable[..., dict[str, Any] | None] | None = None,
        expand_fn: Callable[..., list[dict[str, Any]]] | None = None,
        connect_fn: Callable[..., Any] | None = None,
    ) -> None:
        if lookup_fn is None or expand_fn is None or connect_fn is None:
            from helix_company import connect, expand_company, lookup_lei
            lookup_fn = lookup_fn or lookup_lei
            expand_fn = expand_fn or expand_company
            connect_fn = connect_fn or connect

        self.lei_db = lei_db
        self.rr_db = rr_db
        self.lookup_fn = lookup_fn
        self.expand_fn = expand_fn
        self.connect_fn = connect_fn

    def __call__(self, pivot: HelixFact, iteration: int) -> Iterable[HelixFact]:
        if pivot.fact_type.strip().upper() != ROOT_FACT_TYPE:
            return []
        if not pivot.identifier:
            return []

        conn = self.connect_fn(self.lei_db)
        try:
            root = self.lookup_fn(conn, pivot.identifier)
        finally:
            conn.close()

        if not root:
            raise LookupError(f"Root LEI not found in Level 1 index: {pivot.identifier}")

        entities = self.expand_fn(root, self.lei_db, self.rr_db)
        return [related_entity_to_fact(e, root_lei=pivot.identifier) for e in entities]

DOMAIN_FACT_TYPE = "DOMAIN"


def _candidate_value(candidate: Any, name: str, default: Any = None) -> Any:
    if isinstance(candidate, dict):
        return candidate.get(name, default)
    return getattr(candidate, name, default)


def _enum_value(value: Any) -> str:
    return str(getattr(value, "value", value) or "").upper()


def domain_candidate_to_fact(candidate: Any) -> HelixFact:
    """Map an already-evaluated M4.3B DomainCandidate into M4.3C.

    This bridge does not rescore evidence. domain_candidates.py remains the
    attribution-policy authority.
    """
    domain = str(_candidate_value(candidate, "candidate_domain") or "").strip().lower()
    if not domain:
        raise ValueError("Domain candidate is missing candidate_domain")

    disposition = _enum_value(_candidate_value(candidate, "disposition", "REVIEW"))
    infra_conf = _enum_value(
        _candidate_value(candidate, "infrastructure_attribution_confidence", "UNKNOWN")
    ) or "UNKNOWN"

    if disposition == "AUTO" and infra_conf == "HIGH":
        status, confidence, pivot = "ACCEPTED", "HIGH", True
    elif disposition == "REJECT":
        status, confidence, pivot = "REJECTED", infra_conf or "HIGH", False
    else:
        status, confidence, pivot = "REVIEW", infra_conf or "UNKNOWN", False

    raw_evidence = _candidate_value(candidate, "evidence", []) or []
    evidence: list[dict[str, Any]] = []
    for item in raw_evidence:
        if isinstance(item, dict):
            evidence.append(dict(item))
        elif hasattr(item, "__dict__"):
            row = dict(item.__dict__)
            if "evidence_type" in row:
                row["evidence_type"] = getattr(row["evidence_type"], "value", row["evidence_type"])
            evidence.append(row)

    entity_lei = _candidate_value(candidate, "entity_lei")
    entity_name = _candidate_value(candidate, "entity_name")
    relationships = list(_candidate_value(candidate, "relationships", []) or [])

    return HelixFact(
        fact_type=DOMAIN_FACT_TYPE,
        value=domain,
        subject=str(entity_name) if entity_name else None,
        identifier=domain,
        source="M4.3B_DOMAIN_CANDIDATE",
        confidence=confidence,
        status=status,
        pivot_eligible=pivot,
        evidence=evidence,
        metadata={
            "entity_name": entity_name,
            "entity_lei": entity_lei,
            "relationships": relationships,
            "registrable_domain": _candidate_value(candidate, "registrable_domain"),
            "corporate_confidence": _candidate_value(candidate, "corporate_confidence", "UNKNOWN"),
            "infrastructure_attribution_confidence": infra_conf,
            "m43b_disposition": disposition,
            "review_reason": _candidate_value(candidate, "review_reason"),
            "jurisdiction": _candidate_value(candidate, "jurisdiction"),
        },
    )


def load_domain_candidate_records(path: str) -> list[dict[str, Any]]:
    import json
    with open(path, "r", encoding="utf-8") as fh:
        payload = json.load(fh)
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict) and isinstance(payload.get("candidates"), list):
        return payload["candidates"]
    raise ValueError("Expected a candidate list or {'candidates': [...]} payload")


class DomainCandidateExpansionProvider:
    """Expose evaluated M4.3B domain candidates to matching LEGAL_ENTITY pivots."""

    def __init__(self, candidates: Iterable[Any]) -> None:
        self.by_lei: dict[str, list[Any]] = {}
        for candidate in candidates:
            lei = str(_candidate_value(candidate, "entity_lei") or "").strip()
            if lei:
                self.by_lei.setdefault(lei, []).append(candidate)

    @classmethod
    def from_json(cls, path: str) -> "DomainCandidateExpansionProvider":
        return cls(load_domain_candidate_records(path))

    def __call__(self, pivot: HelixFact, iteration: int) -> Iterable[HelixFact]:
        if pivot.fact_type.strip().upper() != LEGAL_ENTITY_FACT_TYPE:
            return []
        if not pivot.identifier:
            return []
        return [domain_candidate_to_fact(c) for c in self.by_lei.get(pivot.identifier, [])]
