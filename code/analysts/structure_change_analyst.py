"""Guarded LLM analyst for SEC structure-disclosure change packets."""

import json
import re
import urllib.request

from adjudication.structure_change_packet import ALLOWED_DECISIONS


PROMPT_VERSION = "structure-change-analyst-v1"
SYSTEM_PROMPT = """You review one corporate-structure disclosure change using only supplied evidence.
Return one JSON object following the packet's model_contract. Cite only supplied evidence IDs.
The supporting_excerpt must be copied verbatim from one cited evidence record. If the evidence does
not establish an allowed corporate event, return INSUFFICIENT_EVIDENCE. Appearance or disappearance
from disclosure is never by itself proof of acquisition, divestiture, dissolution, or ownership.
Your result is advisory and cannot create trusted graph relationships."""

RESULT_SCHEMA = {
    "type": "object",
    "properties": {
        "decision": {"type": "string", "enum": ALLOWED_DECISIONS},
        "confidence": {"type": "string", "enum": ["HIGH", "MEDIUM", "LOW"]},
        "subject_identity_key": {"type": "string"},
        "supporting_evidence_ids": {"type": "array", "items": {"type": "string"}},
        "conflicting_evidence_ids": {"type": "array", "items": {"type": "string"}},
        "supporting_excerpt": {"type": "string"},
        "event_date": {"type": ["string", "null"]},
        "rationale": {"type": "string"},
    },
    "required": [
        "decision",
        "confidence",
        "subject_identity_key",
        "supporting_evidence_ids",
        "conflicting_evidence_ids",
        "supporting_excerpt",
        "event_date",
        "rationale",
    ],
    "additionalProperties": False,
}


def build_model_input(packet):
    """Exclude collection bookkeeping that cannot support an analyst decision."""
    return {
        key: packet[key]
        for key in (
            "schema_version",
            "packet_id",
            "question",
            "disclosure_change",
            "evidence",
            "model_contract",
        )
        if key in packet
    }


def _extract_json(text):
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.S)
        if not match:
            raise ValueError("Model response did not contain a JSON object")
        return json.loads(match.group(0))


def validate_structure_change_result(raw, packet, *, model="UNKNOWN"):
    if not isinstance(raw, dict):
        raise ValueError("Analyst result must be a JSON object")
    decision = str(raw.get("decision", "")).upper().strip()
    if decision not in ALLOWED_DECISIONS:
        raise ValueError(f"Unsupported structure-change decision: {decision or 'missing'}")
    confidence = str(raw.get("confidence", "")).upper().strip()
    if confidence not in {"HIGH", "MEDIUM", "LOW"}:
        raise ValueError("Confidence must be HIGH, MEDIUM, or LOW")

    change = packet.get("disclosure_change") or {}
    subject_key = str(raw.get("subject_identity_key", "")).strip()
    if subject_key != str(change.get("identity_key", "")).strip():
        raise ValueError("subject_identity_key does not match the disclosure change")

    evidence_by_id = {
        str(e["evidence_id"]): e for e in packet.get("evidence", []) if e.get("evidence_id")
    }
    supporting = _string_list(raw.get("supporting_evidence_ids"))
    conflicting = _string_list(raw.get("conflicting_evidence_ids"))
    unknown = (set(supporting) | set(conflicting)) - set(evidence_by_id)
    if unknown:
        raise ValueError(f"Unknown evidence IDs: {sorted(unknown)}")
    if decision not in {"INSUFFICIENT_EVIDENCE", "CONFLICTING_EVIDENCE"} and not supporting:
        raise ValueError("A supported event decision requires supporting evidence")

    excerpt = str(raw.get("supporting_excerpt") or "").strip()
    if excerpt:
        cited_text = "\n".join(str(evidence_by_id[e].get("text") or "") for e in supporting)
        if excerpt not in cited_text:
            raise ValueError("supporting_excerpt is not verbatim text from cited evidence")
    elif decision not in {"INSUFFICIENT_EVIDENCE", "CONFLICTING_EVIDENCE"}:
        raise ValueError("A supported event decision requires a verbatim supporting_excerpt")

    event_date = raw.get("event_date")
    if event_date not in (None, "") and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(event_date)):
        raise ValueError("event_date must be null or ISO YYYY-MM-DD")

    return {
        "decision": decision,
        "confidence": confidence,
        "subject_identity_key": subject_key,
        "supporting_evidence_ids": supporting,
        "conflicting_evidence_ids": conflicting,
        "supporting_excerpt": excerpt,
        "event_date": event_date or None,
        "rationale": str(raw.get("rationale") or "").strip(),
        "model": model,
        "prompt_version": PROMPT_VERSION,
        "advisory_only": True,
        "creates_trusted_graph_edges": False,
    }


def _string_list(value):
    if not isinstance(value, list):
        raise ValueError("Evidence ID fields must be lists")
    return [str(x) for x in value]


class OllamaStructureChangeAnalyst:
    def __init__(self, model="gemma3:1b", endpoint="http://127.0.0.1:11434/api/chat", timeout=90):
        self.model = model
        self.endpoint = endpoint
        self.timeout = timeout

    def analyze(self, packet):
        body = {
            "model": self.model,
            "stream": False,
            "format": RESULT_SCHEMA,
            "think": False,
            "options": {"temperature": 0, "num_predict": 600},
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": "Return only the required JSON object.\n"
                    + json.dumps(build_model_input(packet), ensure_ascii=False),
                },
            ],
        }
        request = urllib.request.Request(
            self.endpoint,
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            payload = json.loads(response.read().decode())
        content = ((payload.get("message") or {}).get("content") or "").strip()
        return validate_structure_change_result(
            _extract_json(content), packet, model=self.model
        )
