import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"code"))
from iterative_expansion import *

def t(kind,value,status="ACCEPTED",confidence="HIGH",pivot=True):
 return HelixFact(kind,value,source="TEST",status=status,confidence=confidence,pivot_eligible=pivot)

def test_recursive():
 def p(x,n):
  if x.fact_type=="COMPANY": return [t("LEGAL_ENTITY","Hawk-Eye Innovations Limited")]
  if x.fact_type=="LEGAL_ENTITY": return [t("DOMAIN","hawkeyeinnovations.com")]
  return []
 r=run_expansion([t("COMPANY","Sony")],[p]); d={(f.fact_type,f.value):f for f in r.facts}
 assert d[("DOMAIN","hawkeyeinnovations.com")].iteration_discovered==2 and r.converged

def test_review_no_pivot():
 calls=[]
 def p(x,n): calls.append(x.value); return [t("DOMAIN","garbage.example","REVIEW","UNKNOWN",False)]
 r=run_expansion([t("COMPANY","Sony")],[p]); assert calls==["Sony"] and r.stop_reason=="NO_NEW_TRUSTED_PIVOTS"

def test_dedupe():
 def a(x,n): return [HelixFact("DOMAIN","sony.com",status="ACCEPTED",confidence="HIGH",pivot_eligible=True,evidence=[{"p":"a"}])] if x.fact_type=="COMPANY" else []
 def b(x,n): return [HelixFact("DOMAIN","SONY.COM",status="ACCEPTED",confidence="HIGH",pivot_eligible=True,evidence=[{"p":"b"}])] if x.fact_type=="COMPANY" else []
 r=run_expansion([t("COMPANY","Sony")],[a,b]); ds=[f for f in r.facts if f.fact_type=="DOMAIN"]; assert len(ds)==1 and len(ds[0].evidence)==2

def test_failure_isolated():
 def bad(x,n): raise RuntimeError("boom")
 def good(x,n): return [t("LEGAL_ENTITY","Sony Europe B.V.")] if x.fact_type=="COMPANY" else []
 r=run_expansion([t("COMPANY","Sony")],[bad,good]); assert any(f.value=="Sony Europe B.V." for f in r.facts) and r.iterations[0].provider_errors

def test_cap():
 def p(x,n): return [t("OTHER",f"generation-{n}")]
 r=run_expansion([t("COMPANY","Sony")],[p],max_iterations=3); assert not r.converged and r.stop_reason=="MAX_ITERATIONS_REACHED"

def test_no_seed_pivot():
 r=run_expansion([t("COMPANY","Sony","REVIEW","UNKNOWN",False)],[]); assert r.converged and r.iterations_run==0

cases=[test_recursive,test_review_no_pivot,test_dedupe,test_failure_isolated,test_cap,test_no_seed_pivot]
for c in cases: c(); print("PASS",c.__name__)
print(f"\n{len(cases)} passed / 0 failed")
