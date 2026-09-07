from __future__ import annotations

import json
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from ..models import Address, InfrastructureIdentity


def _vcard_props(entity: dict[str, Any]) -> dict[str, list[Any]]:
    card = entity.get("vcardArray")
    out: dict[str, list[Any]] = {}
    if not isinstance(card, list) or len(card) != 2 or not isinstance(card[1], list):
        return out
    for prop in card[1]:
        if isinstance(prop, list) and len(prop) >= 4:
            out.setdefault(str(prop[0]).lower(), []).append(prop[3])
    return out


def _flatten_address(value: Any) -> Address | None:
    # jCard ADR is [po-box, extended, street, locality, region, postal, country]
    if not isinstance(value, list):
        return None
    padded = list(value) + [""] * (7 - len(value))
    street = padded[2]
    lines = street if isinstance(street, list) else [street]
    lines = [str(x).strip() for x in lines if x and str(x).strip()]
    addr = Address(
        lines=lines,
        city=str(padded[3]).strip() or None,
        region=str(padded[4]).strip() or None,
        postal_code=str(padded[5]).strip() or None,
        country=str(padded[6]).strip() or None,
    )
    return addr if addr.compact() else None


def parse_domain_rdap(data: dict[str, Any]) -> InfrastructureIdentity:
    domain = data.get("ldhName") or data.get("unicodeName") or ""
    orgs: list[str] = []
    addresses: list[Address] = []
    country: str | None = None

    # Prefer registrant entities. Some servers redact this entirely; absence is
    # unknown evidence, not evidence of no relationship.
    for entity in data.get("entities", []) or []:
        if not isinstance(entity, dict):
            continue
        roles = {str(x).lower() for x in entity.get("roles", []) or []}
        if "registrant" not in roles:
            continue
        props = _vcard_props(entity)
        for key in ("org", "fn"):
            for value in props.get(key, []):
                if value and str(value).strip() and str(value).strip() not in orgs:
                    orgs.append(str(value).strip())
        for value in props.get("adr", []):
            addr = _flatten_address(value)
            if addr:
                addresses.append(addr)
                country = country or addr.country

    dates: dict[str, str] = {}
    for event in data.get("events", []) or []:
        if isinstance(event, dict) and event.get("eventAction") and event.get("eventDate"):
            dates[str(event["eventAction"])] = str(event["eventDate"])

    return InfrastructureIdentity(
        provider="rdap",
        resource_type="domain",
        resource=str(domain).lower(),
        organization_names=orgs,
        addresses=addresses,
        country=country,
        registration_dates=dates,
        raw=data,
    )


def load_rdap_file(path: str | Path) -> InfrastructureIdentity:
    return parse_domain_rdap(json.loads(Path(path).read_text()))


def fetch_domain(domain: str, timeout: int = 30) -> InfrastructureIdentity:
    # rdap.org performs standards-based service discovery and is convenient for
    # an MVP. A production adapter can replace this with direct IANA bootstrap.
    url = "https://rdap.org/domain/" + urllib.parse.quote(domain.strip().lower())
    req = urllib.request.Request(url, headers={"User-Agent": "CorporationHelix-MVP/0.1"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return parse_domain_rdap(json.loads(resp.read().decode("utf-8")))
