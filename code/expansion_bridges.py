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


def domain_candidate_to_fact(candidate: Any) -> HelixFact:
    """Convert an already-evaluated M4.3B DomainCandidate into an M4.3C fact.

    The domain-candidate policy remains authoritative. This bridge does not
    rescore evidence and never upgrades a REVIEW candidate because its related
    corporate entity has HIGH confidence.
    """
    from domain_candidates import Disposition, InfrastructureConfidence

    disposition = candidate.disposition
    infra_confidence = candidate.infrastructure_attribution_confidence

    if hasattr(disposition, "value"):
        disposition_value = disposition.value
    else:
        disposition_value = str(disposition)

    if hasattr(infra_confidence, "value"):
        confidence_value = infra_confidence.value
    else:
        confidence_value = str(infra_confidence)

    disposition_value = disposition_value.upper()
    confidence_value = confidence_value.upper()

    if disposition_value == Disposition.AUTO.value:
        status = "ACCEPTED"
    elif disposition_value == Disposition.REJECT.value:
        status = "REJECTED"
    else:
        status = "REVIEW"

    pivot_eligible = (
        disposition_value == Disposition.AUTO.value
        and confidence_value == InfrastructureConfidence.HIGH.value
    )

    # DomainEvidence contains enums, so use the candidate's canonical serializer
    # when available to keep evidence JSON-safe and auditable.
    if hasattr(candidate, "to_dict"):
        serialized = candidate.to_dict()
        evidence = list(serialized.get("evidence") or [])
    else:
        serialized = {}
        evidence = []

    return HelixFact(
        fact_type=DOMAIN_FACT_TYPE,
        value=str(candidate.candidate_domain),
        subject=str(candidate.entity_name),
        identifier=(str(candidate.entity_lei) if candidate.entity_lei else None),
        source="DOMAIN_CANDIDATES",
        confidence=confidence_value,
        status=status,
        pivot_eligible=pivot_eligible,
        evidence=evidence,
        metadata={
            "entity_name": candidate.entity_name,
            "entity_lei": candidate.entity_lei,
            "relationships": list(candidate.relationships or []),
            "jurisdiction": candidate.jurisdiction,
            "registrable_domain": candidate.registrable_domain,
            "corporate_confidence": candidate.corporate_confidence,
            "infrastructure_attribution_confidence": confidence_value,
            "domain_disposition": disposition_value,
            "review_reason": candidate.review_reason,
            "policy_source": "M4.3B_DOMAIN_CANDIDATES",
        },
    )


class DomainCandidateExpansionProvider:
    """Generic M4.3C adapter for an existing domain-candidate producer.

    ``candidate_fn`` receives the current trusted corporate pivot and iteration
    number and returns already-evaluated DomainCandidate objects. The provider
    converts those records to HelixFacts; it does not perform attribution.
    """

    def __init__(
        self,
        candidate_fn: Callable[[HelixFact, int], Iterable[Any]],
        *,
        accepted_pivot_types: Iterable[str] = (ROOT_FACT_TYPE, LEGAL_ENTITY_FACT_TYPE),
    ) -> None:
        self.candidate_fn = candidate_fn
        self.accepted_pivot_types = {str(x).strip().upper() for x in accepted_pivot_types}

    def __call__(self, pivot: HelixFact, iteration: int) -> Iterable[HelixFact]:
        if pivot.fact_type.strip().upper() not in self.accepted_pivot_types:
            return []
        candidates = self.candidate_fn(pivot, iteration) or []
        return [domain_candidate_to_fact(candidate) for candidate in candidates]


class SeededOfficialSiteDomainProvider:
    """M4.3C bridge from trusted LEGAL_ENTITY pivots into M4.3B domain policy.

    Seed URLs are candidate-discovery inputs only.  They do not become trusted
    domain facts unless the existing M4.3B discovery/verifier emits evidence
    that evaluates to AUTO/HIGH.
    """

    def __init__(
        self,
        seeds: Iterable[dict[str, Any]],
        *,
        verify_official: bool = True,
        timeout: int = 20,
        observation_fn: Callable[..., list[dict[str, Any]]] | None = None,
        candidates_fn: Callable[..., Iterable[Any]] | None = None,
    ) -> None:
        if observation_fn is None:
            from domain_discovery import build_discovery_observations
            observation_fn = build_discovery_observations
        if candidates_fn is None:
            from domain_candidates import candidates_from_observations
            candidates_fn = candidates_from_observations

        self.seeds = [dict(seed) for seed in seeds]
        self.verify_official = verify_official
        self.timeout = timeout
        self.observation_fn = observation_fn
        self.candidates_fn = candidates_fn

    @staticmethod
    def _entity_from_fact(pivot: HelixFact) -> Any:
        from domain_candidates import CorporateEntity

        return CorporateEntity(
            entity_name=pivot.value,
            entity_lei=pivot.identifier,
            relationships=list(pivot.metadata.get("relationships") or []),
            corporate_confidence=str(
                pivot.metadata.get("corporate_confidence") or pivot.confidence or "UNKNOWN"
            ).upper(),
            jurisdiction=pivot.metadata.get("jurisdiction"),
            source=pivot.source,
        )

    @staticmethod
    def _seed_matches(pivot: HelixFact, seed: dict[str, Any]) -> bool:
        seed_lei = seed.get("entity_lei") or seed.get("lei")
        if seed_lei and pivot.identifier:
            return str(seed_lei) == str(pivot.identifier)

        seed_name = seed.get("entity_name") or seed.get("name")
        if seed_name:
            return str(seed_name).casefold().strip() == pivot.value.casefold().strip()

        return False

    def __call__(self, pivot: HelixFact, iteration: int) -> Iterable[HelixFact]:
        if pivot.fact_type.strip().upper() != LEGAL_ENTITY_FACT_TYPE:
            return []

        matching_seeds = [seed for seed in self.seeds if self._seed_matches(pivot, seed)]
        if not matching_seeds:
            return []

        entity = self._entity_from_fact(pivot)
        observations = self.observation_fn(
            [entity],
            matching_seeds,
            verify_official=self.verify_official,
            timeout=self.timeout,
        )
        candidates = self.candidates_fn([entity], observations) or []
        return [domain_candidate_to_fact(candidate) for candidate in candidates]

class DiscoveringOfficialSiteDomainProvider:
    """Zero-knowledge LEGAL_ENTITY -> web discovery -> M4.3B attribution bridge.

    Search results are candidate provenance only. A domain becomes recursive
    only if the existing verifier + M4.3B policy promote it to AUTO/HIGH.
    """

    def __init__(
        self,
        *,
        max_results_per_entity: int = 5,
        verify_official: bool = True,
        timeout: int = 20,
        discovery_fn=None,
        observation_fn=None,
        candidates_fn=None,
    ) -> None:
        if discovery_fn is None or observation_fn is None:
            from domain_discovery import (
                build_discovery_observations,
                discover_all_entity_seeds,
            )
            discovery_fn = discovery_fn or discover_all_entity_seeds
            observation_fn = observation_fn or build_discovery_observations

        if candidates_fn is None:
            from domain_candidates import candidates_from_observations
            candidates_fn = candidates_fn or candidates_from_observations

        self.max_results_per_entity = max(1, int(max_results_per_entity))
        self.verify_official = verify_official
        self.timeout = timeout
        self.discovery_fn = discovery_fn
        self.observation_fn = observation_fn
        self.candidates_fn = candidates_fn
        self.search_errors = []

    @staticmethod
    def _entity_from_fact(pivot: HelixFact):
        from domain_candidates import CorporateEntity

        return CorporateEntity(
            entity_name=pivot.value,
            entity_lei=pivot.identifier,
            relationships=list(pivot.metadata.get("relationships") or []),
            corporate_confidence=str(
                pivot.metadata.get("corporate_confidence")
                or pivot.confidence
                or "UNKNOWN"
            ).upper(),
            jurisdiction=pivot.metadata.get("jurisdiction"),
            source=pivot.source,
        )

    def __call__(self, pivot: HelixFact, iteration: int):
        if pivot.fact_type.strip().upper() != LEGAL_ENTITY_FACT_TYPE:
            return []

        entity = self._entity_from_fact(pivot)

        seeds, errors = self.discovery_fn(
            [entity],
            max_results_per_entity=self.max_results_per_entity,
            timeout=self.timeout,
        )

        if errors:
            self.search_errors.extend(errors)

        if not seeds:
            return []

        observations = self.observation_fn(
            [entity],
            seeds,
            verify_official=self.verify_official,
            timeout=self.timeout,
        )

        candidates = self.candidates_fn([entity], observations) or []
        return [domain_candidate_to_fact(candidate) for candidate in candidates]

