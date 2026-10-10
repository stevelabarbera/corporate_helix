"""Deterministic rules for explicit corporate-structure evidence."""

from __future__ import annotations

import re
from datetime import datetime


RULE_VERSION = "structure-change-rules-v1"
_EXPLICIT_MERGER = re.compile(
    r"This entity was merged into\s+(?P<survivor>.+?)\s+effective\s+"
    r"(?P<date>[A-Z][a-z]+ \d{1,2}, \d{4})\.",
    flags=re.I,
)


def infer_explicit_structure_change(packet):
    """Return an advisory result only for an unambiguous explicit statement."""
    change = packet.get("disclosure_change") or {}
    subject_key = str(change.get("identity_key") or "").strip()
    subject_names = {subject_key}
    for side in ("previous_disclosure", "current_disclosure"):
        disclosure = change.get(side) or {}
        subject_names.update(str(name).strip() for name in disclosure.get("names", []))
    subject_names.discard("")

    for evidence in packet.get("evidence", []):
        text = str(evidence.get("text") or "")
        if not any(name.casefold() in text.casefold() for name in subject_names):
            continue
        match = _EXPLICIT_MERGER.search(text)
        if not match:
            continue
        event_date = datetime.strptime(match.group("date"), "%B %d, %Y").date().isoformat()
        survivor = match.group("survivor").strip()
        return {
            "decision": "SUPPORTED_MERGER",
            "confidence": "HIGH",
            "subject_identity_key": subject_key,
            "surviving_entity_text": survivor,
            "supporting_evidence_ids": [str(evidence["evidence_id"])],
            "conflicting_evidence_ids": [],
            "supporting_excerpt": match.group(0),
            "event_date": event_date,
            "rationale": "The cited evidence explicitly states that the subject entity was merged into the named surviving entity.",
            "rule_version": RULE_VERSION,
            "advisory_only": True,
            "creates_trusted_graph_edges": False,
        }
    return None
