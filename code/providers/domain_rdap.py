from __future__ import annotations

"""RDAP domain observation provider for Corporation Helix M4.3B.

This module deliberately returns raw/structured RDAP observations only. It does
not decide whether a corporate entity owns a domain.
"""

import json
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class RdapAddress:
    lines: list[str] = field(default_factory=list)
    city: str | None = None
    region: str | None = None
    postal_code: str | None = None
    country: str | None = None

    def compact(self) -> str:
        parts = [*self.lines, self.city, self.region, self.country, self.postal_code]
        return ", ".join(str(x).strip() for x in parts if x and str(x).strip())


@dataclass(frozen=True)
class RdapDomainObservation:
    domain: str
    organization_names: list[str] = field(default_factory=list)
    addresses: list[RdapAddress] = field(default_factory=list)
    country: str | None = None
    registration_dates: dict[str, str] = field(default_factory=dict)
    source_url: str | None = None
    raw: dict[str, Any] = field(default_factory=dict, repr=False)


def _vcard_props(entity: dict[str, Any]) -> dict[str, list[Any]]:
    card = entity.get("vcardArray")
    out: dict[str, list[Any]] = {}
    if not isinstance(card, list) or len(card) != 2 or not isinstance(card[1], list):
        return out
    for prop in card[1]:
        if isinstance(prop, list) and len(prop) >= 4:
            out.setdefault(str(prop[0]).lower(), []).append(prop[3])
    return out


def _flatten_address(value: Any) -> RdapAddress | None:
    # jCard ADR: [po-box, extended, street, locality, region, postal, country]
    if not isinstance(value, list):
        return None
    padded = list(value) + [""] * (7 - len(value))
    street = padded[2]
    lines = street if isinstance(street, list) else [street]
    lines = [str(x).strip() for x in lines if x and str(x).strip()]
    addr = RdapAddress(
        lines=lines,
        city=str(padded[3]).strip() or None,
        region=str(padded[4]).strip() or None,
        postal_code=str(padded[5]).strip() or None,
        country=str(padded[6]).strip() or None,
    )
    return addr if addr.compact() else None


def parse_domain_rdap(data: dict[str, Any], source_url: str | None = None) -> RdapDomainObservation:
    domain = str(data.get("ldhName") or data.get("unicodeName") or "").lower()
    orgs: list[str] = []
    addresses: list[RdapAddress] = []
    country: str | None = None

    # Preserve the recovered behavior: registrant absence/redaction is UNKNOWN,
    # never negative evidence.
    for entity in data.get("entities", []) or []:
        if not isinstance(entity, dict):
            continue
        roles = {str(x).lower() for x in entity.get("roles", []) or []}
        if "registrant" not in roles:
            continue
        props = _vcard_props(entity)
        for key in ("org", "fn"):
            for value in props.get(key, []):
                text = str(value).strip() if value is not None else ""
                if text and text not in orgs:
                    orgs.append(text)
        for value in props.get("adr", []):
            addr = _flatten_address(value)
            if addr:
                addresses.append(addr)
                country = country or addr.country

    dates: dict[str, str] = {}
    for event in data.get("events", []) or []:
        if isinstance(event, dict) and event.get("eventAction") and event.get("eventDate"):
            dates[str(event["eventAction"])] = str(event["eventDate"])

    return RdapDomainObservation(
        domain=domain,
        organization_names=orgs,
        addresses=addresses,
        country=country,
        registration_dates=dates,
        source_url=source_url,
        raw=data,
    )


def load_rdap_file(path: str | Path) -> RdapDomainObservation:
    return parse_domain_rdap(json.loads(Path(path).read_text(encoding="utf-8")), source_url=str(path))


def fetch_domain(domain: str, timeout: int = 30) -> RdapDomainObservation:
    # Preserve the recovered MVP transport for now. This can later be swapped for
    # direct IANA bootstrap without changing the evidence contract.
    clean = domain.strip().lower()
    url = "https://rdap.org/domain/" + urllib.parse.quote(clean)
    req = urllib.request.Request(url, headers={"User-Agent": "CorporationHelix-M4.3B/0.1"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return parse_domain_rdap(data, source_url=url)
