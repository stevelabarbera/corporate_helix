#!/usr/bin/env python3
from __future__ import annotations
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "code"))
from expansion_bridges import DomainCandidateExpansionProvider, domain_candidate_to_fact
from iterative_expansion import HelixFact, run_expansion

def candidate(disposition="AUTO", confidence="HIGH", domain="example.com"):
    return {"entity_name":"Example Legal Entity","entity_lei":"LEI123","relationships":["DIRECT_ACCOUNTING_CHILD"],
    "candidate_domain":domain,"registrable_domain":domain,"corporate_confidence":"HIGH",
    "infrastructure_attribution_confidence":confidence,"evidence":[{"provider":"fixture","evidence_type":"OFFICIAL_WEBSITE","supports_attribution":True}],
    "disposition":disposition,"review_reason":"fixture","jurisdiction":"US"}

def legal():
    return HelixFact("LEGAL_ENTITY","Example Legal Entity",identifier="LEI123",source="GLEIF",confidence="HIGH",status="ACCEPTED",pivot_eligible=True)

def test_auto_high_becomes_pivot():
    f=domain_candidate_to_fact(candidate())
    assert f.status=="ACCEPTED" and f.confidence=="HIGH" and f.can_pivot()

def test_review_never_pivots():
    f=domain_candidate_to_fact(candidate("REVIEW","MEDIUM"))
    assert f.status=="REVIEW" and not f.can_pivot()

def test_reject_never_pivots():
    f=domain_candidate_to_fact(candidate("REJECT","HIGH"))
    assert f.status=="REJECTED" and not f.can_pivot()

def test_auto_without_high_stays_review():
    f=domain_candidate_to_fact(candidate("AUTO","MEDIUM"))
    assert f.status=="REVIEW" and not f.can_pivot()

def test_provider_matches_entity_lei():
    p=DomainCandidateExpansionProvider([candidate()])
    out=list(p(legal(),1)); assert len(out)==1 and out[0].value=="example.com"

def test_real_iteration_promotes_domain_frontier():
    p=DomainCandidateExpansionProvider([candidate()])
    r=run_expansion([legal()],[p],max_iterations=3)
    ds=[f for f in r.facts if f.fact_type=="DOMAIN"]
    assert len(ds)==1 and ds[0].can_pivot()
    assert r.iterations[0].new_pivot_count==1

def main():
    tests=[test_auto_high_becomes_pivot,test_review_never_pivots,test_reject_never_pivots,test_auto_without_high_stays_review,test_provider_matches_entity_lei,test_real_iteration_promotes_domain_frontier]
    failed=0
    for t in tests:
        try: t(); print("PASS",t.__name__)
        except Exception as e: failed+=1; print("FAIL",t.__name__,e)
    print(f"\n{len(tests)-failed} passed / {failed} failed")
    raise SystemExit(1 if failed else 0)
if __name__=="__main__": main()
