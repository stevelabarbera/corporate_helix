from __future__ import annotations
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))

from evidence_contract import EvidenceCapability, EvidenceAvailability
from parsers.asm_mapping import ASMFieldMapping, map_asm_record, map_asm_records


def by_capability(observations, capability):
    return [o for o in observations if o.capability is capability]


def test_default_flat_dotted_mapping():
    obs = map_asm_record({
        "domain": "sony.com",
        "ip": "192.0.2.10",
        "ip.asn": 64500,
        "ip.asn.org": "Sony Corporation",
        "ssl.subject.org": "Sony Corporation",
        "ssl.san": ["www.sony.com"],
    }, expected_entity_name="Sony Corporation")
    assert len(obs) == 2
    ip = by_capability(obs, EvidenceCapability.IP_ASN_OWNERSHIP)[0]
    tls = by_capability(obs, EvidenceCapability.TLS_CERTIFICATE)[0]
    assert ip.supports_attribution is True
    assert tls.supports_attribution is True


def test_nested_mapping():
    obs = map_asm_record({
        "domain": "example.com",
        "ip": "192.0.2.20",
        "ip": {"address": "192.0.2.20", "asn": {"number": 64501, "org": "Example Corp"}},
        "ssl": {"subject": {"org": "Example Corp"}, "san": ["www.example.com"]},
    }, mapping=ASMFieldMapping(
        ip="ip.address",
        asn="ip.asn.number",
        asn_org="ip.asn.org",
    ))
    assert len(obs) == 2


def test_custom_vendor_fields():
    mapping = ASMFieldMapping(
        domain="asset.hostname",
        ip="asset.address",
        asn="network.autnum",
        asn_org="network.owner",
        tls_org="certificate.organization",
        tls_sans="certificate.sans",
    )
    obs = map_asm_record({
        "asset": {"hostname": "example.com", "address": "192.0.2.30"},
        "network": {"autnum": "AS64502", "owner": "Example Corp"},
        "certificate": {"organization": "Example Corp", "sans": ["www.example.com"]},
    }, mapping=mapping)
    assert len(obs) == 2


def test_ip_asn_only_record():
    obs = map_asm_record({
        "ip": "192.0.2.40",
        "ip.asn": 64503,
        "ip.asn.org": "Example Networks LLC",
    })
    assert len(obs) == 1
    assert obs[0].capability is EvidenceCapability.IP_ASN_OWNERSHIP


def test_tls_only_record():
    obs = map_asm_record({
        "domain": "example.com",
        "ssl.subject.org": "Example Corp",
    })
    assert len(obs) == 1
    assert obs[0].capability is EvidenceCapability.TLS_CERTIFICATE


def test_tls_domain_without_org_preserves_missing_evidence():
    obs = map_asm_record({"domain": "example.com"})
    assert len(obs) == 1
    assert obs[0].capability is EvidenceCapability.TLS_CERTIFICATE
    assert obs[0].availability is EvidenceAvailability.MISSING


def test_empty_record_produces_no_observations():
    assert map_asm_record({}) == []


def test_org_without_ip_or_asn_does_not_invent_subject():
    assert map_asm_record({"ip.asn.org": "Example Corp"}) == []


def test_san_can_supply_tls_subject():
    obs = map_asm_record({
        "ssl.subject.org": "Example Corp",
        "ssl.san": ["api.example.com"],
    })
    assert len(obs) == 1
    assert obs[0].subject == "api.example.com"


def test_batch_mapping():
    obs = map_asm_records([
        {"domain": "a.example", "ssl.subject.org": "Example Corp"},
        {"ip": "192.0.2.50", "ip.asn": 64504, "ip.asn.org": "Example Corp"},
    ])
    assert len(obs) == 2


def test_provider_prefix_and_reference():
    obs = map_asm_record({
        "domain": "example.com",
        "ssl.subject.org": "Example Corp",
    }, provider_prefix="customer-acme", reference="row-17")
    assert obs[0].provider == "customer-acme-tls"
    assert obs[0].reference == "row-17"
