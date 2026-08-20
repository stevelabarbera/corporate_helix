from __future__ import annotations
from dataclasses import dataclass, asdict, field
from typing import Any
from .entity import EntityCandidate
from .relationship import RelationshipAssertion

@dataclass
class ProviderResult:
    provider: str
    query: str
    resolved_name: str | None = None
    provider_entity_id: str | None = None
    entities: list[EntityCandidate] = field(default_factory=list)
    relationships: list[RelationshipAssertion] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
