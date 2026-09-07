#!/usr/bin/env python3
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "code"))

from domain_candidates import (
    CorporateEntity,
    Disposition,
    DomainEvidence,
    EvidenceType,
    InfrastructureConfidence,
    evaluate_evidence,
)
from providers.domain_rdap import parse_domain_rdap
from rdap_evidence import interpret_rdap


def _google_rdap(country="BE"):
    return parse_domain_rdap({
        "ldhName": "example.be",
        "entities": [{
            "roles": ["registrant"],
            "vcardArray": ["vcard", [
                ["version", {}, "text", "4.0"],
                ["org", {}, "text", "Google Belgium"],
                ["adr", {}, "text", ["", "", "Chaussée d'Etterbeek 180", "Brussel", "", "1040", country]],
            ]],
        }],
    }, source_url="fixture:google-belgium")


def test_raw_rdap_org_is_not_auto():
    e = DomainEvidence(provider="RDAP", evidence_type=EvidenceType.RDAP_ORG, observed_value="Google Belgium")
    conf, disposition, _ = evaluate_evidence([e])
    assert conf is InfrastructureConfidence.LOW
    assert disposition is Disposition.REVIEW


def test_raw_rdap_registrant_is_not_auto():
    e = DomainEvidence(provider="RDAP", evidence_type=EvidenceType.RDAP_REGISTRANT, observed_value="Google Belgium")
    conf, disposition, _ = evaluate_evidence([e])
    assert conf is InfrastructureConfidence.LOW
    assert disposition is Disposition.REVIEW


def test_interpreted_rdap_name_and_country_can_auto():
    entity = CorporateEntity(entity_name="GOOGLE BELGIUM", entity_lei="TEST", jurisdiction="BE")
    ev = interpret_rdap(entity, _google_rdap())
    assert any(x.evidence_type is EvidenceType.RDAP_ATTRIBUTION_MATCH for x in ev)
    conf, disposition, _ = evaluate_evidence(ev)
    assert conf is InfrastructureConfidence.HIGH
    assert disposition is Disposition.AUTO


def test_country_conflict_rejects_interpreted_rdap():
    entity = CorporateEntity(entity_name="GOOGLE BELGIUM", entity_lei="TEST", jurisdiction="US-DE")
    ev = interpret_rdap(entity, _google_rdap())
    assert any(x.evidence_type is EvidenceType.RDAP_ATTRIBUTION_CONFLICT for x in ev)
    conf, disposition, _ = evaluate_evidence(ev)
    assert conf is InfrastructureConfidence.HIGH
    assert disposition is Disposition.REJECT


def test_redacted_registrant_is_unknown_not_negative():
    entity = CorporateEntity(entity_name="GOOGLE BELGIUM", entity_lei="TEST", jurisdiction="BE")
    rdap = parse_domain_rdap({"ldhName": "example.be", "entities": []}, source_url="fixture:redacted")
    ev = interpret_rdap(entity, rdap)
    assert ev == []
    conf, disposition, _ = evaluate_evidence(ev)
    assert conf is InfrastructureConfidence.UNKNOWN
    assert disposition is Disposition.REVIEW


if __name__ == "__main__":
    tests = [
        test_raw_rdap_org_is_not_auto,
        test_raw_rdap_registrant_is_not_auto,
        test_interpreted_rdap_name_and_country_can_auto,
        test_country_conflict_rejects_interpreted_rdap,
        test_redacted_registrant_is_unknown_not_negative,
    ]
    failed = 0
    for t in tests:
        try:
            t()
            print("PASS", t.__name__)
        except Exception as exc:
            failed += 1
            print("FAIL", t.__name__, "-", exc)
    print(f"\n{len(tests)-failed} passed / {failed} failed")
    raise SystemExit(1 if failed else 0)
