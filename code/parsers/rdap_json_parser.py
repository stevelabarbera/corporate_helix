#!/usr/bin/env python3
"""Parse user-supplied RFC 9083-shaped RDAP JSON into Helix evidence.

No network collection is performed here.
"""
from __future__ import annotations
import json
import re
from pathlib import Path
from typing import Any
from evidence_contract import EvidenceAvailability, EvidenceCapability, InfrastructureObservation

_REDACTION_MARKERS = ("redacted", "privacy", "gdpr", "not disclosed", "data protected", "withheld", "masked")

def _normalize_name(value: str) -> str:
    return " ".join(re.sub(r"[^\w\s]", " ", value.casefold()).split())

def _names_plausibly_match(a: str, b: str) -> bool:
    a, b = _normalize_name(a), _normalize_name(b)
    return bool(a and b and (a == b or a in b or b in a))

def _contains_redaction(value: Any) -> bool:
    if isinstance(value, str):
        return any(marker in value.casefold() for marker in _REDACTION_MARKERS)
    if isinstance(value, dict):
        return any(_contains_redaction(v) for v in value.values())
    if isinstance(value, list):
        return any(_contains_redaction(v) for v in value)
    return False

def _roles(entity: dict[str, Any]) -> set[str]:
    roles = entity.get("roles") or []
    if isinstance(roles, str):
        roles = [roles]
    return {str(role).casefold() for role in roles}

def _vcard_fields(entity: dict[str, Any]) -> dict[str, list[str]]:
    card = entity.get("vcardArray")
    if not isinstance(card, list) or len(card) != 2 or not isinstance(card[1], list):
        return {}
    fields = {}
    for item in card[1]:
        if not isinstance(item, list) or len(item) < 4:
            continue
        key, value = str(item[0]).casefold(), item[3]
        if isinstance(value, str) and value.strip():
            fields.setdefault(key, []).append(value.strip())
    return fields

def _registrant_entities(payload: dict[str, Any]) -> list[dict[str, Any]]:
    entities = payload.get("entities") or []
    if not isinstance(entities, list):
        return []
    return [e for e in entities if isinstance(e, dict) and "registrant" in _roles(e)]

def _registrant_identity(entity: dict[str, Any]) -> str | None:
    fields = _vcard_fields(entity)
    for key in ("org", "fn"):
        values = fields.get(key) or []
        if values:
            return values[0]
    return None

def parse_rdap_json(payload: dict[str, Any], domain: str | None = None, *,
                    provider: str = "user-supplied-rdap",
                    expected_entity_name: str | None = None,
                    reference: str | None = None) -> InfrastructureObservation:
    if not isinstance(payload, dict):
        raise ValueError("RDAP payload must be a JSON object.")
    subject = domain or payload.get("ldhName") or payload.get("unicodeName")
    if not subject:
        raise ValueError("RDAP payload does not identify a domain; provide domain explicitly.")
    subject = str(subject).strip().rstrip(".").lower()

    registrants = _registrant_entities(payload)
    if not registrants:
        availability = EvidenceAvailability.INCONCLUSIVE if _contains_redaction(payload) else EvidenceAvailability.MISSING
        reason = "privacy_redaction_detected" if availability is EvidenceAvailability.INCONCLUSIVE else "no_registrant_entity_found"
        return InfrastructureObservation(
            capability=EvidenceCapability.RDAP_WHOIS, provider=provider, subject=subject,
            availability=availability, reference=reference,
            raw={"parsed_from": "rdap_json", "reason": reason})

    identities = [x for x in (_registrant_identity(e) for e in registrants) if x]
    if not identities:
        return InfrastructureObservation(
            capability=EvidenceCapability.RDAP_WHOIS, provider=provider, subject=subject,
            availability=EvidenceAvailability.INCONCLUSIVE, reference=reference,
            raw={"parsed_from": "rdap_json", "reason": "registrant_present_without_identity"})

    unique = list(dict.fromkeys(identities))
    if len(unique) > 1:
        return InfrastructureObservation(
            capability=EvidenceCapability.RDAP_WHOIS, provider=provider, subject=subject,
            observed_value=" | ".join(unique), availability=EvidenceAvailability.INCONCLUSIVE,
            reference=reference, raw={"parsed_from": "rdap_json",
            "reason": "multiple_registrant_identities", "registrants": unique})

    registrant = unique[0]
    if _contains_redaction(registrant):
        return InfrastructureObservation(
            capability=EvidenceCapability.RDAP_WHOIS, provider=provider, subject=subject,
            availability=EvidenceAvailability.INCONCLUSIVE, reference=reference,
            raw={"parsed_from": "rdap_json", "reason": "privacy_redaction_detected"})

    supports = None if not expected_entity_name else _names_plausibly_match(registrant, expected_entity_name)
    return InfrastructureObservation(
        capability=EvidenceCapability.RDAP_WHOIS, provider=provider, subject=subject,
        observed_value=registrant, availability=EvidenceAvailability.PROVIDED,
        supports_attribution=supports, reference=reference, raw={"parsed_from": "rdap_json"})

def load_rdap_json(path: Path, domain: str | None = None, *,
                   provider: str = "user-supplied-rdap",
                   expected_entity_name: str | None = None) -> InfrastructureObservation:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return parse_rdap_json(payload, domain, provider=provider,
                           expected_entity_name=expected_entity_name, reference=str(path))
