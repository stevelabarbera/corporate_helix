from __future__ import annotations
from dataclasses import dataclass, asdict, field
from typing import Any, Optional

@dataclass
class EntityCandidate:
    provider: str
    provider_entity_id: Optional[str]
    legal_name: str
    jurisdiction: Optional[str] = None
    registration_number: Optional[str] = None
    status: Optional[str] = None
    former_names: list[str] = field(default_factory=list)
    addresses: list[str] = field(default_factory=list)
    attributes: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
