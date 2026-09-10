from __future__ import annotations
import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"code"))
from evidence_contract import EvidenceAvailability,EvidenceCapability
from parsers.tls_certificate_parser import parse_tls_certificate

def test_subject_org_is_provided():
    o=parse_tls_certificate({"domain":"WWW.SONY.COM","subject_org":"Sony Corporation"})
    assert o.capability is EvidenceCapability.TLS_CERTIFICATE
    assert o.availability is EvidenceAvailability.PROVIDED
    assert o.subject=="www.sony.com" and o.observed_value=="Sony Corporation"

def test_subject_cn_can_supply_subject():
    assert parse_tls_certificate({"subject_cn":"portal.example.com","organization":"Example Corporation"}).subject=="portal.example.com"

def test_san_can_supply_subject():
    o=parse_tls_certificate({"sans":["api.example.com","www.example.com"],"org":"Example Corporation"})
    assert o.subject=="api.example.com"
    assert o.raw["sans"]==["api.example.com","www.example.com"]

def test_missing_org_is_missing():
    o=parse_tls_certificate({"domain":"example.com","sans":["www.example.com"]})
    assert o.availability is EvidenceAvailability.MISSING
    assert o.supports_attribution is None

def test_redacted_org_is_inconclusive():
    assert parse_tls_certificate({"domain":"example.com","subject_org":"REDACTED"}).availability is EvidenceAvailability.INCONCLUSIVE

def test_expected_entity_match_true():
    assert parse_tls_certificate({"domain":"sony.com","subject_org":"Sony Corporation"},expected_entity_name="Sony Corporation").supports_attribution is True

def test_expected_entity_mismatch_false():
    assert parse_tls_certificate({"domain":"example.com","subject_org":"Example Networks LLC"},expected_entity_name="Sony Corporation").supports_attribution is False

def test_no_expected_entity_none():
    assert parse_tls_certificate({"domain":"example.com","subject_org":"Example Networks LLC"}).supports_attribution is None

def test_explicit_domain_overrides_payload():
    assert parse_tls_certificate({"domain":"wrong.example.com","subject_org":"Example Corp"},domain="RIGHT.EXAMPLE.COM.").subject=="right.example.com"

def test_missing_subject_raises():
    with pytest.raises(ValueError):
        parse_tls_certificate({"subject_org":"Example Corp"})
