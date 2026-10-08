"""Evidence packet for LLM-assisted structure-disclosure change review."""

import hashlib
import json


ALLOWED_DECISIONS = [
    "SUPPORTED_ACQUISITION",
    "SUPPORTED_DIVESTITURE",
    "SUPPORTED_RENAME",
    "SUPPORTED_CONVERSION",
    "SUPPORTED_DISSOLUTION",
    "POSSIBLE_INTERNAL_REORGANIZATION",
    "REPORTING_SCOPE_CHANGE",
    "INSUFFICIENT_EVIDENCE",
    "CONFLICTING_EVIDENCE",
]


def _packet_id(change):
    raw = json.dumps({
        "identity_key": change.get("identity_key"),
        "previous_filing_date": change.get("previous_filing_date"),
        "current_filing_date": change.get("current_filing_date"),
        "change_type": change.get("change_type"),
    }, sort_keys=True)
    return "scp:" + hashlib.sha256(raw.encode()).hexdigest()[:20]


def build_structure_change_packet(change, evidence):
    evidence_ids = [str(e.get("evidence_id", "")).strip() for e in evidence]
    if any(not evidence_id for evidence_id in evidence_ids):
        raise ValueError("Every evidence record requires an evidence_id")
    if len(evidence_ids) != len(set(evidence_ids)):
        raise ValueError("Evidence IDs must be unique within a packet")

    return {
        "schema_version": "structure-change-evidence-packet-v1",
        "packet_id": _packet_id(change),
        "question": "What, if anything, does the supplied evidence establish about this disclosure change?",
        "disclosure_change": change,
        "evidence": evidence,
        "model_contract": {
            "reason_only_from_supplied_evidence": True,
            "allowed_decisions": ALLOWED_DECISIONS,
            "confidence_allowed": ["HIGH", "MEDIUM", "LOW"],
            "required_fields": [
                "decision",
                "confidence",
                "subject_identity_key",
                "supporting_evidence_ids",
                "conflicting_evidence_ids",
                "supporting_excerpt",
                "event_date",
                "rationale",
            ],
            "prohibited_behavior": [
                "Do not use model memory as evidence.",
                "Do not cite an evidence ID absent from this packet.",
                "Do not invent or paraphrase the supporting excerpt.",
                "Do not treat disclosure disappearance as proof of divestiture or dissolution.",
                "Do not create trusted graph edges.",
            ],
        },
        "adjudication": {"status": "PENDING", "llm": None, "human": None, "final": None},
    }
