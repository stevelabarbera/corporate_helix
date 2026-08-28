from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class Address:
    lines: list[str] = field(default_factory=list)
    city: str | None = None
    region: str | None = None
    country: str | None = None
    postal_code: str | None = None
    mail_routing: str | None = None
    address_type: str | None = None

    def compact(self) -> str:
        parts = [self.mail_routing, *self.lines, self.city, self.region, self.country, self.postal_code]
        return ", ".join(str(p).strip() for p in parts if p and str(p).strip())


@dataclass
class LegalEntityEvent:
    event_type: str
    event_status: str | None = None
    group_type: str | None = None
    effective_date: str | None = None
    recorded_date: str | None = None
    validation_documents: str | None = None
    validation_reference: str | None = None
    affected_fields: list[dict[str, str | None]] = field(default_factory=list)


@dataclass
class EntityCandidate:
    provider: str
    provider_id: str
    legal_name: str
    other_names: list[str] = field(default_factory=list)
    legal_address: Address | None = None
    headquarters_address: Address | None = None
    other_addresses: list[Address] = field(default_factory=list)
    jurisdiction: str | None = None
    registration_authority: str | None = None
    registration_id: str | None = None
    category: str | None = None
    subcategory: str | None = None
    legal_form: str | None = None
    entity_status: str | None = None
    entity_creation_date: str | None = None
    registration_status: str | None = None
    validation_status: str | None = None
    initial_registration_date: str | None = None
    last_update_date: str | None = None
    next_renewal_date: str | None = None
    successor_ids: list[str] = field(default_factory=list)
    successor_names: list[str] = field(default_factory=list)
    events: list[LegalEntityEvent] = field(default_factory=list)
    conformity: str | None = None
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d.pop("raw", None)
        return d


@dataclass
class RelationshipEvidence:
    provider: str
    child_id: str
    parent_id: str | None
    relationship_type: str
    relationship_status: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    reporting_exception: str | None = None
    source_reference: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class InfrastructureIdentity:
    provider: str
    resource_type: str
    resource: str
    organization_names: list[str] = field(default_factory=list)
    addresses: list[Address] = field(default_factory=list)
    country: str | None = None
    registration_dates: dict[str, str] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict, repr=False)


@dataclass
class MatchSignal:
    name: str
    result: str
    score: float | None = None
    detail: str | None = None


@dataclass
class CandidateMatch:
    infrastructure_resource: str
    entity: EntityCandidate
    signals: list[MatchSignal]
    decision: str
    rank_score: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "infrastructure_resource": self.infrastructure_resource,
            "entity": self.entity.to_dict(),
            "signals": [asdict(x) for x in self.signals],
            "decision": self.decision,
            "rank_score": round(self.rank_score, 4),
        }
