from __future__ import annotations
from dataclasses import dataclass, asdict, field
from typing import Any, Optional
from .evidence import Evidence

@dataclass
class RelationshipAssertion:
    provider: str
    subject_name: str
    predicate: str
    object_name: str
    jurisdiction: Optional[str] = None
    ownership_percent: Optional[float] = None
    relationship_status: Optional[str] = None
    former_names: list[str] = field(default_factory=list)
    evidence: list[Evidence] = field(default_factory=list)
    attributes: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
