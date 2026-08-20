from __future__ import annotations
from dataclasses import dataclass, asdict, field
from typing import Any, Optional

@dataclass
class Evidence:
    provider: str
    evidence_type: str
    source_url: Optional[str] = None
    source_document_id: Optional[str] = None
    source_date: Optional[str] = None
    as_of_date: Optional[str] = None
    extraction_method: Optional[str] = None
    coverage: Optional[str] = None
    raw_record: Any = None
    attributes: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
