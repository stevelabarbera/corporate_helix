from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from parsers.ip_asn_parser import parse_ip_asn_evidence
from parsers.tls_certificate_parser import parse_tls_certificate


@dataclass(frozen=True)
class ASMFieldMapping:
    domain: str = "domain"
    ip: str | None = "ip"
    asn: str | None = "ip.asn"
    asn_org: str | None = "ip.asn.org"
    tls_org: str | None = "ssl.subject.org"
    tls_sans: str | None = "ssl.san"


def _get(record: Mapping[str, Any], path: str | None) -> Any:
    if not path:
        return None
    if path in record:
        return record[path]
    current: Any = record
    for part in path.split("."):
        if not isinstance(current, Mapping) or part not in current:
            return None
        current = current[part]
    return current


def _present(value: Any) -> bool:
    return value is not None and (not isinstance(value, str) or bool(value.strip()))


def _associate_domain(observation: Any, domain: Any) -> Any:
    """Preserve the enclosing ASM asset's domain separately from evidence subject."""
    if _present(domain):
        observation.raw["candidate_domain"] = str(domain).strip().rstrip(".").lower()
    return observation


def map_asm_record(
    record: Mapping[str, Any],
    *,
    mapping: ASMFieldMapping = ASMFieldMapping(),
    expected_entity_name: str | None = None,
    provider_prefix: str = "user-supplied-asm",
    reference: str | None = None,
) -> list:
    if not isinstance(record, Mapping):
        raise ValueError("ASM record must be an object/mapping.")

    domain = _get(record, mapping.domain)
    observations = []

    ip = _get(record, mapping.ip)
    asn = _get(record, mapping.asn)
    asn_org = _get(record, mapping.asn_org)
    if any(_present(v) for v in (ip, asn, asn_org)):
        payload = {}
        if _present(ip):
            payload["ip"] = ip
        if _present(asn):
            payload["asn"] = asn
        if _present(asn_org):
            payload["asn_org"] = asn_org
        if _present(ip) or _present(asn):
            observation = parse_ip_asn_evidence(
                payload,
                expected_entity_name=expected_entity_name,
                provider=f"{provider_prefix}-ip-asn",
                reference=reference,
            )
            observations.append(_associate_domain(observation, domain))

    tls_org = _get(record, mapping.tls_org)
    tls_sans = _get(record, mapping.tls_sans)
    if any(_present(v) for v in (domain, tls_org, tls_sans)):
        payload = {}
        if _present(domain):
            payload["domain"] = domain
        if _present(tls_org):
            payload["subject_org"] = tls_org
        if _present(tls_sans):
            payload["sans"] = tls_sans
        if _present(domain) or _present(tls_sans):
            observations.append(
                parse_tls_certificate(
                    payload,
                    expected_entity_name=expected_entity_name,
                    provider=f"{provider_prefix}-tls",
                    reference=reference,
                )
            )

    return observations


def map_asm_records(
    records: Sequence[Mapping[str, Any]],
    *,
    mapping: ASMFieldMapping = ASMFieldMapping(),
    expected_entity_name: str | None = None,
    provider_prefix: str = "user-supplied-asm",
    reference: str | None = None,
) -> list:
    observations = []
    for record in records:
        observations.extend(
            map_asm_record(
                record,
                mapping=mapping,
                expected_entity_name=expected_entity_name,
                provider_prefix=provider_prefix,
                reference=reference,
            )
        )
    return observations
