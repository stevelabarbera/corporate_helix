#!/usr/bin/env python3
from __future__ import annotations
import re
from typing import Any
from evidence_contract import EvidenceAvailability, EvidenceCapability, InfrastructureObservation

_REDACTION_MARKERS=("redacted","privacy","not disclosed","withheld","masked","unknown")

def _norm_name(value:str)->str:
    return " ".join(re.sub(r"[^\w\s]"," ",value.casefold()).split())

def _match(a:str,b:str)->bool:
    a,b=_norm_name(a),_norm_name(b)
    return bool(a and b and (a==b or a in b or b in a))

def _norm_domain(value:Any)->str|None:
    if value is None or str(value).strip()=="":
        return None
    return str(value).strip().rstrip(".").lower()

def _first(payload,*keys):
    for key in keys:
        value=payload.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None

def parse_tls_certificate(payload:dict[str,Any],*,domain:str|None=None,
                          provider:str="user-supplied-tls",
                          expected_entity_name:str|None=None,
                          reference:str|None=None)->InfrastructureObservation:
    if not isinstance(payload,dict):
        raise ValueError("TLS certificate payload must be an object.")
    subject=_norm_domain(domain or payload.get("domain") or payload.get("hostname")
                         or payload.get("common_name") or payload.get("subject_cn"))
    san_values=payload.get("sans") or payload.get("san") or payload.get("subject_alt_names") or []
    if isinstance(san_values,str):
        san_values=[san_values]
    sans=[_norm_domain(v) for v in san_values if _norm_domain(v)]
    if not subject and sans:
        subject=sans[0]
    if not subject:
        raise ValueError("TLS certificate evidence requires a domain/CN/SAN subject.")
    org=_first(payload,"subject_org","subject_organization","organization","org","subject_o")
    raw={"parsed_from":"tls_certificate","sans":sans}
    if not org:
        raw["reason"]="no_certificate_organization_found"
        return InfrastructureObservation(capability=EvidenceCapability.TLS_CERTIFICATE,
            provider=provider,subject=subject,availability=EvidenceAvailability.MISSING,
            reference=reference,raw=raw)
    if any(marker in org.casefold() for marker in _REDACTION_MARKERS):
        raw["reason"]="certificate_organization_inconclusive"
        return InfrastructureObservation(capability=EvidenceCapability.TLS_CERTIFICATE,
            provider=provider,subject=subject,availability=EvidenceAvailability.INCONCLUSIVE,
            reference=reference,raw=raw)
    supports=None if not expected_entity_name else _match(org,expected_entity_name)
    return InfrastructureObservation(capability=EvidenceCapability.TLS_CERTIFICATE,
        provider=provider,subject=subject,observed_value=org,
        availability=EvidenceAvailability.PROVIDED,supports_attribution=supports,
        reference=reference,raw=raw)
