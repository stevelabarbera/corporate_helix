from __future__ import annotations
import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"code"))
from evidence_contract import EvidenceAvailability,EvidenceCapability
from parsers.ip_asn_parser import parse_ip_asn_evidence

def test_ip_asn_owner():
 o=parse_ip_asn_evidence({"ip":"8.8.8.8","asn":15169,"organization":"Google LLC"})
 assert o.capability is EvidenceCapability.IP_ASN_OWNERSHIP and o.availability is EvidenceAvailability.PROVIDED
 assert o.subject=="8.8.8.8" and o.observed_value=="Google LLC" and o.raw["asn"]=="AS15169"
def test_asn_only():
 o=parse_ip_asn_evidence({"asn":"AS64500","org":"Example Corporation"}); assert o.subject=="AS64500"
def test_ip_only():
 o=parse_ip_asn_evidence({"ip_address":"192.0.2.10","owner":"Example Holdings LLC"}); assert o.subject=="192.0.2.10"
def test_missing_owner():
 assert parse_ip_asn_evidence({"ip":"192.0.2.11","asn":"64501"}).availability is EvidenceAvailability.MISSING
def test_redacted():
 assert parse_ip_asn_evidence({"asn":"AS64502","organization":"REDACTED"}).availability is EvidenceAvailability.INCONCLUSIVE
def test_match():
 assert parse_ip_asn_evidence({"asn":64503,"asn_org":"Sony Corporation"},expected_entity_name="Sony Corporation").supports_attribution is True
def test_mismatch():
 assert parse_ip_asn_evidence({"asn":64503,"asn_org":"Example Networks LLC"},expected_entity_name="Sony Corporation").supports_attribution is False
def test_no_expected():
 assert parse_ip_asn_evidence({"asn":64503,"asn_org":"Example Networks LLC"}).supports_attribution is None
def test_asn_normalized():
 assert parse_ip_asn_evidence({"asn":"  as0015169 ","organization":"Google LLC"}).raw["asn"]=="AS15169"
def test_invalid_ip():
 with pytest.raises(ValueError): parse_ip_asn_evidence({"ip":"999.999.999.999","organization":"Example Corp"})
def test_invalid_asn():
 with pytest.raises(ValueError): parse_ip_asn_evidence({"asn":"AS-NOT-A-NUMBER","organization":"Example Corp"})
def test_missing_subject():
 with pytest.raises(ValueError): parse_ip_asn_evidence({"organization":"Example Corp"})
