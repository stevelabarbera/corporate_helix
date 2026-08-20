#!/usr/bin/env python3
from adjudication.engine import evaluate_candidate

def node(i,n,nn,b,j,aliases=None,ids=None):
    return {"node_id":i,"canonical_name":n,"canonical_name_normalized":nn,"legal_name_base":b,"jurisdiction":j,"aliases":aliases or [],"provider_entity_ids":ids or []}

def main():
    tests=[]; g={"relationships":[]}
    tests.append(("Sony cross-jurisdiction",evaluate_candidate(g,node("a","Sony Interactive Entertainment Inc.","sony interactive entertainment inc","sony interactive entertainment","JP"),node("b","Sony Interactive Entertainment LLC","sony interactive entertainment llc","sony interactive entertainment","US"),"SAME_ENTITY"),"REJECT","DISTINCT_BY_JURISDICTION"))
    tests.append(("Sentinel Labs cross-jurisdiction",evaluate_candidate(g,node("a","Sentinel Labs Limited","sentinel labs limited","sentinel labs","GB"),node("b","Sentinel Labs Pte Limited","sentinel labs pte limited","sentinel labs","SG"),"SAME_ENTITY"),"REJECT","DISTINCT_BY_JURISDICTION"))
    tests.append(("Exact provider identifier",evaluate_candidate(g,node("a","Example Corp","example corp","example","US",ids=["lei:X"]),node("b","Example Corporation","example corporation","example","US",ids=["lei:X"]),"SAME_ENTITY"),"ACCEPT","EXPLICIT_CONTINUITY_OR_IDENTIFIER"))
    tests.append(("Former-name continuity",evaluate_candidate(g,node("a","Scalyr LLC","scalyr llc","scalyr","US",aliases=[{"name_normalized":"scalyr inc"}]),node("b","Scalyr Inc","scalyr inc","scalyr","US"),"SAME_ENTITY"),"ACCEPT","EXPLICIT_CONTINUITY_OR_IDENTIFIER"))
    tests.append(("Ambiguous same-jurisdiction",evaluate_candidate(g,node("a","Acme Holdings LLC","acme holdings llc","acme holdings","US"),node("b","Acme Holdings Inc","acme holdings inc","acme holdings","US"),"SAME_ENTITY"),"REVIEW","AMBIGUOUS_SIGNAL_AGREEMENT"))
    g2={"relationships":[{"subject_node_id":"child","object_node_id":"parent","predicate":"SUBSIDIARY_OF"}]}
    tests.append(("Explicit subsidiary",evaluate_candidate(g2,node("child","Child LLC","child llc","child","US"),node("parent","Parent Corp","parent corp","parent","US"),"SUBSIDIARY_OF"),"ACCEPT","EXPLICIT_CONTINUITY_OR_IDENTIFIER"))
    failed=0
    for name,r,ed,er in tests:
        ok=r["decision"]==ed and r["resolution_reason"]==er
        print(("PASS" if ok else "FAIL"),name,"->",r["decision"],r["resolution_reason"],"score",r["score"])
        if not ok: failed+=1
    print(f"\n{len(tests)-failed} passed / {failed} failed")
    raise SystemExit(1 if failed else 0)
if __name__=="__main__": main()
