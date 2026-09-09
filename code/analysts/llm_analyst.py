from __future__ import annotations

import json
import re
import urllib.request
from dataclasses import dataclass
from typing import Any

from analysts.base import AnalystDecision, AnalystDecisionType


ALLOWED_TYPES = {x.value for x in AnalystDecisionType}
PROMPT_VERSION = "m43c-analyst-v2"


SYSTEM_PROMPT = """You are an investigation assistant inside Corporation Helix.
Your job is to PROPOSE things to investigate, not declare corporate or infrastructure ownership.

You may use your general background knowledge to generate plausible investigation leads. A proposal
is NOT evidence and will NOT be trusted without deterministic corroboration, so do not refuse merely
because ownership has not already been proven.

Prefer useful aliases, brands, likely official-domain candidates, and targeted search queries.
For a recognizable organization, normally return 1 to 5 useful proposals. Use ABSTAIN only when you
truly cannot suggest a meaningful investigation lead.

Return JSON only using exactly this shape:
{
  "decisions": [
    {
      "decision_type": "PROPOSE_ALIAS|PROPOSE_BRAND|PROPOSE_DOMAIN|PROPOSE_SEARCH|PROPOSE_ENTITY|ABSTAIN",
      "value": "string",
      "confidence": "UNKNOWN|LOW|MEDIUM|HIGH",
      "reason": "short reason",
      "evidence_ids": []
    }
  ]
}

Never use ACCEPT_REVIEW or REJECT_REVIEW in this discovery task.
Never claim a proposed domain is owned by the company merely because the name looks related.
"""


@dataclass(frozen=True)
class AnalystRunDebug:
    raw_content: str
    parsed_payload: Any
    normalized_items: list[dict[str, Any]]
    accepted_count: int
    dropped_items: list[dict[str, Any]]


def _extract_json(text: str) -> Any:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"(\[.*\]|\{.*\})", text, flags=re.S)
        if not match:
            raise ValueError("Model response did not contain JSON")
        return json.loads(match.group(1))


def _normalize_response(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, dict):
        for key in ("decisions", "suggestions", "proposals", "results", "items"):
            if isinstance(payload.get(key), list):
                payload = payload[key]
                break
        else:
            payload = [payload]
    if not isinstance(payload, list):
        raise ValueError("Analyst response must be a JSON list or object containing a decision list")
    return [x for x in payload if isinstance(x, dict)]


def _canonical_decision_type(item: dict[str, Any]) -> str:
    raw = str(
        item.get("decision_type")
        or item.get("type")
        or item.get("action")
        or item.get("proposal_type")
        or ""
    ).upper().strip().replace("-", "_").replace(" ", "_")

    aliases = {
        "ALIAS": "PROPOSE_ALIAS",
        "BRAND": "PROPOSE_BRAND",
        "DOMAIN": "PROPOSE_DOMAIN",
        "SEARCH": "PROPOSE_SEARCH",
        "SEARCH_QUERY": "PROPOSE_SEARCH",
        "ENTITY": "PROPOSE_ENTITY",
        "NONE": "ABSTAIN",
    }
    return aliases.get(raw, raw)


def _decision_value(item: dict[str, Any]) -> str:
    for key in ("value", "proposal", "candidate", "domain", "alias", "brand", "query", "entity"):
        value = item.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def _validate_decisions_with_debug(
    raw: Any,
    *,
    subject: str,
    subject_identifier: str | None,
    model: str,
    iteration: int,
) -> tuple[list[AnalystDecision], list[dict[str, Any]], list[dict[str, Any]]]:
    decisions: list[AnalystDecision] = []
    normalized = _normalize_response(raw)
    dropped: list[dict[str, Any]] = []

    for item in normalized:
        dtype = _canonical_decision_type(item)
        if dtype not in ALLOWED_TYPES:
            dropped.append({"reason": "unsupported_decision_type", "item": item})
            continue

        value = _decision_value(item)
        reason = str(item.get("reason") or item.get("rationale") or "").strip()
        confidence = str(item.get("confidence") or "UNKNOWN").upper().strip()
        if confidence not in {"UNKNOWN", "LOW", "MEDIUM", "HIGH"}:
            confidence = "UNKNOWN"
        if dtype != AnalystDecisionType.ABSTAIN.value and not value:
            dropped.append({"reason": "missing_value", "item": item})
            continue

        decisions.append(
            AnalystDecision(
                decision_type=AnalystDecisionType(dtype),
                value=value,
                subject=subject,
                subject_identifier=subject_identifier,
                confidence=confidence,
                reason=reason,
                model=model,
                prompt_version=PROMPT_VERSION,
                iteration=iteration,
                evidence_ids=[str(x) for x in item.get("evidence_ids", []) if x is not None]
                if isinstance(item.get("evidence_ids", []), list)
                else [],
                metadata={
                    "advisory_only": True,
                    "requires_deterministic_corroboration": True,
                },
            )
        )
    return decisions, normalized, dropped


def validate_decisions(
    raw: Any,
    *,
    subject: str,
    subject_identifier: str | None,
    model: str,
    iteration: int,
) -> list[AnalystDecision]:
    decisions, _, _ = _validate_decisions_with_debug(
        raw,
        subject=subject,
        subject_identifier=subject_identifier,
        model=model,
        iteration=iteration,
    )
    return decisions


class OllamaAnalyst:
    def __init__(self, model: str = "gemma3:1b", endpoint: str = "http://127.0.0.1:11434/api/chat", timeout: int = 90):
        self.model = model
        self.endpoint = endpoint
        self.timeout = timeout
        self.last_debug: AnalystRunDebug | None = None

    def analyze(
        self,
        *,
        subject: str,
        subject_identifier: str | None = None,
        jurisdiction: str | None = None,
        relationships: list[str] | None = None,
        known_facts: list[dict[str, Any]] | None = None,
        observations: list[dict[str, Any]] | None = None,
        unresolved_candidates: list[dict[str, Any]] | None = None,
        iteration: int = 0,
    ) -> list[AnalystDecision]:
        request_context = {
            "subject": subject,
            "subject_identifier": subject_identifier,
            "jurisdiction": jurisdiction,
            "relationships": relationships or [],
            "known_facts": known_facts or [],
            "observations": observations or [],
            "unresolved_candidates": unresolved_candidates or [],
            "task": "Generate plausible investigation leads. Proposals are advisory and do not assert ownership.",
        }
        body = {
            "model": self.model,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0},
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(request_context, ensure_ascii=False)},
            ],
        }
        req = urllib.request.Request(
            self.endpoint,
            data=json.dumps(body).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        content = ((payload.get("message") or {}).get("content") or "").strip()
        parsed = _extract_json(content)
        decisions, normalized, dropped = _validate_decisions_with_debug(
            parsed,
            subject=subject,
            subject_identifier=subject_identifier,
            model=self.model,
            iteration=iteration,
        )
        self.last_debug = AnalystRunDebug(
            raw_content=content,
            parsed_payload=parsed,
            normalized_items=normalized,
            accepted_count=len(decisions),
            dropped_items=dropped,
        )
        return decisions
