from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class AnalystDecisionType(str, Enum):
    PROPOSE_ALIAS = "PROPOSE_ALIAS"
    PROPOSE_BRAND = "PROPOSE_BRAND"
    PROPOSE_DOMAIN = "PROPOSE_DOMAIN"
    PROPOSE_SEARCH = "PROPOSE_SEARCH"
    PROPOSE_ENTITY = "PROPOSE_ENTITY"
    ACCEPT_REVIEW = "ACCEPT_REVIEW"
    REJECT_REVIEW = "REJECT_REVIEW"
    ABSTAIN = "ABSTAIN"


@dataclass
class AnalystDecision:
    decision_type: AnalystDecisionType
    value: str
    subject: str
    subject_identifier: str | None = None
    confidence: str = "UNKNOWN"
    reason: str = ""
    model: str = "UNKNOWN"
    prompt_version: str = "m43c-analyst-v1"
    iteration: int = 0
    evidence_ids: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["decision_type"] = self.decision_type.value
        return data

    @property
    def pivot_eligible(self) -> bool:
        # Non-negotiable M4.3C rule: analyst output is investigation advice,
        # never trusted recursive knowledge by itself.
        return False
