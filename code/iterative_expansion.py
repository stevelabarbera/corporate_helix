from __future__ import annotations
from dataclasses import dataclass,field,asdict
from typing import Any,Callable,Iterable
import json

@dataclass
class HelixFact:
    fact_type:str; value:str
    subject:str|None=None; identifier:str|None=None; source:str="UNKNOWN"
    confidence:str="UNKNOWN"; status:str="REVIEW"; pivot_eligible:bool=False
    iteration_discovered:int=0
    evidence:list[dict[str,Any]]=field(default_factory=list)
    metadata:dict[str,Any]=field(default_factory=dict)
    def key(self): return (self.fact_type.strip().upper(),self.value.strip().casefold(),(self.identifier or "").strip().casefold())
    def can_pivot(self): return self.status=="ACCEPTED" and self.confidence=="HIGH" and self.pivot_eligible

@dataclass
class ExpansionIteration:
    iteration:int; frontier_count:int; discovered_count:int; new_fact_count:int; new_pivot_count:int
    provider_errors:list[dict[str,str]]=field(default_factory=list)

@dataclass
class ExpansionResult:
    converged:bool; stop_reason:str; iterations_run:int; facts:list[HelixFact]; iterations:list[ExpansionIteration]
    def to_dict(self):
        return {"schema":"corporation-helix-iterative-expansion/v1","converged":self.converged,
        "stop_reason":self.stop_reason,"iterations_run":self.iterations_run,
        "summary":{"facts":len(self.facts),"accepted":sum(f.status=="ACCEPTED" for f in self.facts),
        "review":sum(f.status=="REVIEW" for f in self.facts),"rejected":sum(f.status=="REJECTED" for f in self.facts),
        "pivot_eligible":sum(f.can_pivot() for f in self.facts)},
        "iterations":[asdict(i) for i in self.iterations],"facts":[asdict(f) for f in self.facts]}

Provider=Callable[[HelixFact,int],Iterable[HelixFact]]

def merge_fact(a,b):
    promoted=False
    seen={json.dumps(e,sort_keys=True,default=str) for e in a.evidence}
    for e in b.evidence:
        k=json.dumps(e,sort_keys=True,default=str)
        if k not in seen: a.evidence.append(e); seen.add(k)
    for k,v in b.metadata.items(): a.metadata.setdefault(k,v)
    cr={"UNKNOWN":0,"LOW":1,"MEDIUM":2,"HIGH":3}; sr={"REJECTED":0,"REVIEW":1,"ACCEPTED":2}
    if cr.get(b.confidence,0)>cr.get(a.confidence,0): a.confidence=b.confidence; promoted=True
    # REJECTED is sticky: a status ordinal comparison alone must never promote a
    # fact out of REJECTED, since REJECTED usually represents explicit
    # contradictory/distinctness evidence, not merely "low confidence." Silently
    # letting a later, unrelated ACCEPTED/REVIEW observation for the same key
    # overwrite that is exactly the false-positive-ASM-scope failure mode this
    # architecture is built to avoid. Flag it for human review instead.
    if a.status=="REJECTED" and b.status!="REJECTED":
        flags=a.metadata.setdefault("review_flags",[])
        flags.append({
            "reason":"conflicting_status_after_rejection",
            "incoming_status":b.status,
            "incoming_confidence":b.confidence,
            "incoming_source":b.source,
        })
    elif sr.get(b.status,0)>sr.get(a.status,0):
        a.status=b.status; promoted=True
    if b.pivot_eligible and not a.pivot_eligible and a.status!="REJECTED":
        a.pivot_eligible=True; promoted=True
    return promoted

def run_expansion(seeds,providers,max_iterations=10):
    providers=list(providers); facts={}
    for s in seeds:
        s.iteration_discovered=0
        if s.key() in facts: merge_fact(facts[s.key()],s)
        else: facts[s.key()]=s
    frontier=[f for f in facts.values() if f.can_pivot()]; records=[]
    if not frontier: return ExpansionResult(True,"NO_PIVOT_ELIGIBLE_SEEDS",0,list(facts.values()),records)
    for n in range(1,max_iterations+1):
        found=[]; errors=[]
        for pivot in frontier:
            for provider in providers:
                try:
                    for f in provider(pivot,n) or []: f.iteration_discovered=n; found.append(f)
                except Exception as e:
                    errors.append({"provider":getattr(provider,"__name__",provider.__class__.__name__),
                    "pivot_type":pivot.fact_type,"pivot_value":pivot.value,"error":f"{type(e).__name__}: {e}"})
        new=0; nxt=[]; queued=set()
        for f in found:
            k=f.key()
            if k not in facts:
                facts[k]=f; new+=1
                if f.can_pivot(): nxt.append(f); queued.add(k)
            else:
                old=facts[k]; was=old.can_pivot()
                if merge_fact(old,f) and not was and old.can_pivot() and k not in queued: nxt.append(old); queued.add(k)
        records.append(ExpansionIteration(n,len(frontier),len(found),new,len(nxt),errors))
        if not nxt: return ExpansionResult(True,"NO_NEW_TRUSTED_PIVOTS",n,list(facts.values()),records)
        frontier=nxt
    return ExpansionResult(False,"MAX_ITERATIONS_REACHED",max_iterations,list(facts.values()),records)
