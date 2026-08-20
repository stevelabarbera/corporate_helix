#!/usr/bin/env python3
import importlib.util, pathlib
spec=importlib.util.spec_from_file_location("oa", pathlib.Path(__file__).with_name("ollama_adjudicate.py"))
oa=importlib.util.module_from_spec(spec); spec.loader.exec_module(oa)

packet={
 "candidate_a":{"canonical_name":"Acme Holdings LLC","jurisdiction":"US"},
 "candidate_b":{"canonical_name":"Acme Holdings Inc","jurisdiction":"US"},
 "deterministic_evaluation":{"signals":{
   "jurisdiction_match":True,"jurisdiction_conflict":False,"shared_address":True,
   "shared_addresses":["100 market street san francisco ca 94105"],
   "exact_provider_identifier":False,"provider_identifier_conflict":False,
   "explicit_former_name_match":False,"exact_legal_name_base":True
 }},
 "evidence_summary":{"same_parent":False,"same_source_document":False,"separately_enumerated":False,
                     "both_have_explicit_subsidiary_edges":False},
 "evidence":[{"evidence_id":"ev:1"},{"evidence_id":"ev:2"}]
}
def result(decision="AMBIGUOUS",confidence="HIGH",rationale="Insufficient evidence.",support=None):
    return {"decision":decision,"confidence":confidence,
            "supporting_evidence_ids":["ev:1"] if support is None else support,
            "conflicting_evidence_ids":[],"rationale":rationale}
cases=[
 ("former-name hallucination",result("SAME_ENTITY","HIGH","The address and former name match, confirming identity."),
  "rationale claims former-name continuity but explicit_former_name_match=false"),
 ("high-confidence identity without grade evidence",result("SAME_ENTITY","HIGH","The same address supports identity."),
  "HIGH-confidence SAME_ENTITY lacks identity-grade evidence"),
 ("identifier hallucination",result("SAME_ENTITY","MEDIUM","The matching registration number supports identity."),
  "rationale claims matching identifier but exact_provider_identifier=false"),
 ("parent hallucination",result("AMBIGUOUS","LOW","They appear to have the same parent."),
  "rationale claims shared parent but same_parent=false"),
 ("jurisdiction hallucination",result("AMBIGUOUS","HIGH","They are registered in different jurisdictions."),
  "rationale claims jurisdiction difference but jurisdiction_match=true"),
 ("distinct decision with same-entity rationale",result("DISTINCT_ENTITY","HIGH","The source entities are identical and confirm the same entity."),
  "DISTINCT_ENTITY rationale asserts sameness/identity"),
 ("high-confidence distinct without grade evidence",result("DISTINCT_ENTITY","HIGH","The records appear different."),
  "HIGH-confidence DISTINCT_ENTITY lacks distinctness-grade evidence"),
]
for name,r,expected in cases:
    errs=oa.consistency_errors(r,packet)
    assert expected in errs,(name,errs)
    print("PASS",name)
good=result("AMBIGUOUS","HIGH",
 "Both records are US entities and share an address, but the supplied evidence contains no exact provider identifier or explicit former-name continuity.",
 support=["ev:1","ev:2"])
assert oa.consistency_errors(good,packet)==[],oa.consistency_errors(good,packet)
print("PASS grounded ambiguous response")
print("\n8 passed / 0 failed")
