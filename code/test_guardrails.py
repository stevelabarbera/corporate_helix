#!/usr/bin/env python3
from adjudication.signals import extract_signals
import importlib.util, pathlib
spec=importlib.util.spec_from_file_location("oa",pathlib.Path(__file__).with_name("ollama_adjudicate.py"))
oa=importlib.util.module_from_spec(spec);spec.loader.exec_module(oa)
def n(i,name):
    return {"node_id":i,"canonical_name":name,"canonical_name_normalized":name.casefold(),
      "legal_name_base":"acme holdings","jurisdiction":"US","provider_entity_ids":[],"aliases":[],
      "source_entities":[{"addresses":["100 Market Street, San Francisco, CA 94105"]}]}
a,b=n("a","Acme Holdings LLC"),n("b","Acme Holdings Inc")
s=extract_signals({"relationships":[]},a,b)
assert s["shared_address"] is True,s
assert s["jurisdiction_match"] is True,s
packet={"candidate_a":a,"candidate_b":b,"question":"same?",
 "deterministic_evaluation":{"signals":s},
 "evidence_summary":{"same_parent":False,"same_source_document":False,"separately_enumerated":False},
 "evidence":[{"evidence_id":"ev:1"},{"evidence_id":"ev:2"}]}
bad={"decision":"AMBIGUOUS","confidence":"HIGH","supporting_evidence_ids":[],
 "conflicting_evidence_ids":[],"rationale":"The entities are in different jurisdictions."}
errs=oa.consistency_errors(bad,packet)
assert "rationale claims jurisdiction difference but jurisdiction_match=true" in errs,errs
unsupported={"decision":"SAME_ENTITY","confidence":"HIGH","supporting_evidence_ids":[],
 "conflicting_evidence_ids":[],"rationale":"They appear identical."}
errs=oa.consistency_errors(unsupported,packet)
assert "conclusive decision has no supporting evidence IDs" in errs,errs
assert "HIGH-confidence SAME_ENTITY lacks identity-grade evidence" in errs,errs
good={"decision":"AMBIGUOUS","confidence":"HIGH","supporting_evidence_ids":["ev:1","ev:2"],
 "conflicting_evidence_ids":[],"rationale":"Both are US records with a shared address, but no identifier or continuity evidence proves identity."}
assert oa.consistency_errors(good,packet)==[],oa.consistency_errors(good,packet)
print("PASS shared-address extraction")
print("PASS jurisdiction contradiction guard")
print("PASS evidence-required conclusive decision guard")
print("PASS valid ambiguous adjudication")
print("\n4 passed / 0 failed")
