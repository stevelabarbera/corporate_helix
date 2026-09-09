#!/usr/bin/env python3
"""Corporation Helix — M4.3E vendor-neutral evidence contract and gap layer."""
from __future__ import annotations
from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Iterable

class EvidenceAvailability(str, Enum):
    PROVIDED="PROVIDED"; MISSING="MISSING"; INCONCLUSIVE="INCONCLUSIVE"; CONTRADICTORY="CONTRADICTORY"

class EvidenceCapability(str, Enum):
    RDAP_WHOIS="RDAP_WHOIS"
    IP_ASN_OWNERSHIP="IP_ASN_OWNERSHIP"
    TLS_CERTIFICATE="TLS_CERTIFICATE"
    DNS="DNS"
    HTTP_LEGAL_PRIVACY="HTTP_LEGAL_PRIVACY"
    CUSTOMER_ASSERTION="CUSTOMER_ASSERTION"

@dataclass(frozen=True)
class InfrastructureObservation:
    capability: EvidenceCapability
    provider: str
    subject: str
    observed_value: str|None=None
    availability: EvidenceAvailability=EvidenceAvailability.PROVIDED
    supports_attribution: bool|None=None
    reference: str|None=None
    raw: dict[str,Any]=field(default_factory=dict)

    @staticmethod
    def from_mapping(data: dict[str,Any]) -> "InfrastructureObservation":
        return InfrastructureObservation(
            capability=EvidenceCapability(str(data["capability"]).upper()),
            provider=str(data.get("provider") or data.get("source") or "UNKNOWN"),
            subject=str(data.get("subject") or data.get("domain") or ""),
            observed_value=None if (data.get("observed_value") or data.get("value")) is None else str(data.get("observed_value") or data.get("value")),
            availability=EvidenceAvailability(str(data.get("availability") or "PROVIDED").upper()),
            supports_attribution=data.get("supports_attribution"),
            reference=None if data.get("reference") is None else str(data["reference"]),
            raw=data.get("raw") or {},
        )

    def to_dict(self):
        d=asdict(self); d["capability"]=self.capability.value; d["availability"]=self.availability.value; return d

@dataclass(frozen=True)
class EvidenceGap:
    subject: str
    capability: EvidenceCapability
    reason: str
    priority: int
    request: str
    def to_dict(self):
        d=asdict(self); d["capability"]=self.capability.value; return d

DEFAULT_ATTRIBUTION_WATERFALL=(
    EvidenceCapability.RDAP_WHOIS,
    EvidenceCapability.IP_ASN_OWNERSHIP,
    EvidenceCapability.TLS_CERTIFICATE,
    EvidenceCapability.HTTP_LEGAL_PRIVACY,
)

_REQUESTS={
 EvidenceCapability.RDAP_WHOIS:"Provide RDAP/WHOIS registrant organization or interpreted ownership evidence.",
 EvidenceCapability.IP_ASN_OWNERSHIP:"Provide resolved IP plus ASN/netblock ownership evidence.",
 EvidenceCapability.TLS_CERTIFICATE:"Provide TLS certificate organization, issuer, SAN, or certificate-history evidence.",
 EvidenceCapability.DNS:"Provide DNS observations relevant to ownership or infrastructure relationships.",
 EvidenceCapability.HTTP_LEGAL_PRIVACY:"Provide legal/privacy/copyright/operator observations from the web property.",
 EvidenceCapability.CUSTOMER_ASSERTION:"Provide an explicit customer/operator attribution assertion if one exists.",
}

def identify_evidence_gaps(subject: str, observations: Iterable[InfrastructureObservation], required: Iterable[EvidenceCapability]=DEFAULT_ATTRIBUTION_WATERFALL) -> list[EvidenceGap]:
    by={}
    for obs in observations: by.setdefault(obs.capability,[]).append(obs)
    gaps=[]
    for priority,cap in enumerate(required,1):
        items=by.get(cap,[])
        if not items:
            gaps.append(EvidenceGap(subject,cap,"Evidence was not provided.",priority,_REQUESTS[cap])); continue
        if any(x.availability is EvidenceAvailability.PROVIDED for x in items): continue
        if any(x.availability is EvidenceAvailability.CONTRADICTORY for x in items): continue
        reason="Evidence was provided but is inconclusive." if any(x.availability is EvidenceAvailability.INCONCLUSIVE for x in items) else "Evidence is explicitly marked missing."
        gaps.append(EvidenceGap(subject,cap,reason,priority,_REQUESTS[cap]))
    return gaps
