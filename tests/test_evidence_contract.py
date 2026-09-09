#!/usr/bin/env python3
import sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; sys.path.insert(0,str(ROOT/"code"))
from evidence_contract import *

def test_no_observations_requests_waterfall():
    g=identify_evidence_gaps("example.com",[])
    assert [x.capability for x in g]==list(DEFAULT_ATTRIBUTION_WATERFALL)
    assert [x.priority for x in g]==[1,2,3,4]

def test_provided_capability_is_not_gap():
    o=[InfrastructureObservation(EvidenceCapability.RDAP_WHOIS,"ASM","example.com","Example Corp")]
    assert EvidenceCapability.RDAP_WHOIS not in {x.capability for x in identify_evidence_gaps("example.com",o)}

def test_redacted_whois_is_inconclusive_gap():
    o=[InfrastructureObservation(EvidenceCapability.RDAP_WHOIS,"ASM","example.com","REDACTED",EvidenceAvailability.INCONCLUSIVE)]
    g=identify_evidence_gaps("example.com",o)
    assert "inconclusive" in next(x for x in g if x.capability is EvidenceCapability.RDAP_WHOIS).reason.lower()

def test_cloud_asn_can_be_inconclusive():
    o=[InfrastructureObservation(EvidenceCapability.IP_ASN_OWNERSHIP,"ASM","example.com","AWS",EvidenceAvailability.INCONCLUSIVE)]
    assert EvidenceCapability.IP_ASN_OWNERSHIP in {x.capability for x in identify_evidence_gaps("example.com",o)}

def test_contradiction_not_called_missing():
    o=[InfrastructureObservation(EvidenceCapability.RDAP_WHOIS,"ASM","example.com","Other Corp",EvidenceAvailability.CONTRADICTORY,False)]
    assert EvidenceCapability.RDAP_WHOIS not in {x.capability for x in identify_evidence_gaps("example.com",o)}

def test_vendor_neutral_mapping():
    o=InfrastructureObservation.from_mapping({"capability":"tls_certificate","source":"SOME_ASM","domain":"example.com","value":"O=Example Corp","supports_attribution":True,"raw":{"san":["example.com"]}})
    assert o.capability is EvidenceCapability.TLS_CERTIFICATE and o.provider=="SOME_ASM" and o.raw["san"]==["example.com"]

TESTS=[test_no_observations_requests_waterfall,test_provided_capability_is_not_gap,test_redacted_whois_is_inconclusive_gap,test_cloud_asn_can_be_inconclusive,test_contradiction_not_called_missing,test_vendor_neutral_mapping]
if __name__=="__main__":
    failures=[]
    for t in TESTS:
        try: t(); print("PASS",t.__name__)
        except Exception as e: failures.append((t.__name__,e)); print("FAIL",t.__name__,e)
    print(f"\n{len(TESTS)-len(failures)} passed / {len(failures)} failed")
    raise SystemExit(1 if failures else 0)
