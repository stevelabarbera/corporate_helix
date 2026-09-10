#!/usr/bin/env python3
"""
Corporation Helix -- whois text parser.

Per the project's architectural rule: Helix does not actively go out and
fetch WHOIS/RDAP itself, even though that's a lightweight lookup. It only
parses whatever the user hands over -- e.g. the output of running
`whois example.com` themselves. This module does exactly that: raw text
in, an InfrastructureObservation out. No network calls anywhere in this
file.

WHOIS output format is NOT standardized across registrars/registries --
this handles the common key variants seen in practice and is deliberately
conservative about what it claims to have parsed. When it can't find a
registrant organization field at all, it reports MISSING rather than
guessing. When it finds clear privacy-redaction language, it reports
INCONCLUSIVE rather than treating an empty/masked field as a negative
signal (that distinction is exactly what evidence_contract.py's
EvidenceAvailability enum exists for).
"""
from __future__ import annotations

import re
from typing import Optional

from evidence_contract import EvidenceAvailability, EvidenceCapability, InfrastructureObservation

# Key variants seen across registrars/registries for the registrant
# organization field. Order matters only in that the first match wins.
_ORG_KEY_PATTERNS = (
    r"Registrant\s+Organization\s*:\s*(.+)",
    r"Registrant\s+Org\s*:\s*(.+)",
    r"org(?:anisation|anization)?\s*:\s*(.+)",  # generic ccTLD-style "Organisation:"
    r"Admin\s+Organization\s*:\s*(.+)",
)

_NAME_KEY_PATTERNS = (
    r"Registrant\s+Name\s*:\s*(.+)",
)

_REDACTION_MARKERS = (
    "redacted for privacy",
    "data protected",
    "not disclosed",
    "privacy protect",
    "whois privacy",
    "on behalf of",  # e.g. "Whois Agent (on behalf of ...)" proxy registrations
    "withheld for privacy",
    "gdpr masked",
)


def _first_match(patterns: tuple[str, ...], text: str) -> Optional[str]:
    for pattern in patterns:
        m = re.search(pattern, text, re.IGNORECASE)
        if m:
            value = m.group(1).strip()
            if value and value not in {".", "-", "N/A", "n/a"}:
                return value
    return None


def _normalize_for_compare(value: str) -> str:
    value = value.casefold()
    value = re.sub(r"[^\w\s]", " ", value)
    return " ".join(value.split())


def _names_plausibly_match(a: str, b: str) -> bool:
    na, nb = _normalize_for_compare(a), _normalize_for_compare(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    # Loose containment check: handles "Sony Corporation" vs
    # "Sony Corporation of America" style variants without claiming a
    # false precision this parser doesn't have.
    return na in nb or nb in na


def parse_whois_text(
    text: str,
    domain: str,
    *,
    provider: str = "user-supplied-whois",
    expected_entity_name: Optional[str] = None,
) -> InfrastructureObservation:
    """
    Parse raw whois command output into a single InfrastructureObservation
    for the RDAP_WHOIS capability.

    If expected_entity_name is given, the parsed registrant is compared
    against it to set supports_attribution. Without it, supports_attribution
    is left None (the caller/analyst still has to make that call) --
    this parser only extracts what the text says, it doesn't decide
    attribution on its own.
    """
    lowered = text.casefold()

    if any(marker in lowered for marker in _REDACTION_MARKERS):
        return InfrastructureObservation(
            capability=EvidenceCapability.RDAP_WHOIS,
            provider=provider,
            subject=domain,
            observed_value=None,
            availability=EvidenceAvailability.INCONCLUSIVE,
            supports_attribution=None,
            reference=None,
            raw={"parsed_from": "whois_text", "reason": "privacy_redaction_detected"},
        )

    registrant = _first_match(_ORG_KEY_PATTERNS, text) or _first_match(_NAME_KEY_PATTERNS, text)

    if not registrant:
        return InfrastructureObservation(
            capability=EvidenceCapability.RDAP_WHOIS,
            provider=provider,
            subject=domain,
            observed_value=None,
            availability=EvidenceAvailability.MISSING,
            supports_attribution=None,
            reference=None,
            raw={"parsed_from": "whois_text", "reason": "no_registrant_field_found"},
        )

    supports_attribution = None
    if expected_entity_name:
        supports_attribution = _names_plausibly_match(registrant, expected_entity_name)

    return InfrastructureObservation(
        capability=EvidenceCapability.RDAP_WHOIS,
        provider=provider,
        subject=domain,
        observed_value=registrant,
        availability=EvidenceAvailability.PROVIDED,
        supports_attribution=supports_attribution,
        reference=None,
        raw={"parsed_from": "whois_text"},
    )
