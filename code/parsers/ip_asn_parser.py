#!/usr/bin/env python3
"""Parse user-supplied IP/ASN ownership evidence into Helix observations.

This adapter performs no network collection. It interprets evidence supplied
by a user, customer, ASM platform, RIR export, or other collector.
"""
from __future__ import annotations

import ipaddress
import re
from typing import Any

from evidence_contract import (
    EvidenceAvailability,
    EvidenceCapability,
    InfrastructureObservation,
)

_REDACTION_MARKERS = (
    "redacted",
    "privacy",
    "not disclosed",
    "withheld",
    "masked",
    "unknown",
)

def _norm_name(value: str) -> str:
    return " ".join(re.sub(r"[^\w\s]", " ", value.casefold()).split())

def _match(a: str, b: str) -> bool:
    a, b = _norm_name(a), _norm_name(b)
    return bool(a and b and (a == b or a in b or b in a))

def _asn(value: Any) -> str | None:
    if value is None or str(value).strip() == "":
        return None
    text = str(value).strip().upper()
    if text.startswith("AS"):
        text = text[2:].strip()
    if not text.isdigit():
        raise ValueError(f"Invalid ASN: {value!r}")
    return f"AS{int(text)}"

def _ip(value: Any) -> str | None:
    if value is None or str(value).strip() == "":
        return None
    return str(ipaddress.ip_address(str(value).strip()))

def parse_ip_asn_evidence(
    payload: dict[str, Any],
    *,
    provider: str = "user-supplied-ip-asn",
    expected_entity_name: str | None = None,
    reference: str | None = None,
) -> InfrastructureObservation:
    if not isinstance(payload, dict):
        raise ValueError("IP/ASN payload must be an object.")

    ip = _ip(payload.get("ip") or payload.get("ip_address"))
    asn = _asn(payload.get("asn") or payload.get("autnum"))

    if not ip and not asn:
        raise ValueError("IP/ASN evidence requires an IP address or ASN.")

    subject = ip or asn

    owner = None
    owner_field = None
    for key in (
        "organization",
        "org",
        "owner",
        "asn_org",
        "as_name",
        "network_name",
        "netname",
    ):
        value = payload.get(key)
        if value is not None and str(value).strip():
            owner = str(value).strip()
            owner_field = key
            break

    raw = {
        "parsed_from": "ip_asn",
        "ip": ip,
        "asn": asn,
    }

    if not owner:
        raw["reason"] = "no_ownership_identity_found"
        return InfrastructureObservation(
            capability=EvidenceCapability.IP_ASN_OWNERSHIP,
            provider=provider,
            subject=subject,
            availability=EvidenceAvailability.MISSING,
            reference=reference,
            raw=raw,
        )

    raw["owner_field"] = owner_field

    if any(marker in owner.casefold() for marker in _REDACTION_MARKERS):
        raw["reason"] = "ownership_identity_inconclusive"
        return InfrastructureObservation(
            capability=EvidenceCapability.IP_ASN_OWNERSHIP,
            provider=provider,
            subject=subject,
            availability=EvidenceAvailability.INCONCLUSIVE,
            reference=reference,
            raw=raw,
        )

    supports_attribution = (
        None
        if not expected_entity_name
        else _match(owner, expected_entity_name)
    )

    return InfrastructureObservation(
        capability=EvidenceCapability.IP_ASN_OWNERSHIP,
        provider=provider,
        subject=subject,
        observed_value=owner,
        availability=EvidenceAvailability.PROVIDED,
        supports_attribution=supports_attribution,
        reference=reference,
        raw=raw,
    )
