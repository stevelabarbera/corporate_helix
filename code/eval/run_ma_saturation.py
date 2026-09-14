#!/usr/bin/env python3
"""Report frozen Helix M&A coverage and saturation. This file does not run or tune the parser."""
from __future__ import annotations
import argparse,json
from pathlib import Path
STAGES=("cik_resolved","filings_retrieved","relevant_text_present","locator_captured","entity_recognized","event_extracted","candidate_emitted")
def load(p): return json.loads(Path(p).read_text())
def labels(xs):
    out=[]; seen=set()
    for x in xs or []:
        x=str(x).strip().upper()
        if x and x not in seen: seen.add(x); out.append(x)
    return out
def summarize(study,result_dir):
    result_dir=Path(result_dir); sp=set(); sf=set(); rows=[]
    stage_counts={s:{"true":0,"false":0,"unknown":0} for s in STAGES}
    for spec in sorted(study["companies"],key=lambda x:x["order"]):
        p=result_dir/f'{spec["id"]}.json'
        if not p.exists():
            rows.append({"order":spec["order"],"company_id":spec["id"],"company":spec["company"],"status":"MISSING"})
            continue
        r=load(p); pipe=r.get("pipeline",{})
        for s in STAGES:
            v=pipe.get(s); stage_counts[s]["true" if v is True else "false" if v is False else "unknown"]+=1
        ps,fs=labels(r.get("observed_primitives")),labels(r.get("failure_classes"))
        np=[x for x in ps if x not in sp]; nf=[x for x in fs if x not in sf]
        sp.update(ps); sf.update(fs)
        rows.append({"order":spec["order"],"company_id":spec["id"],"company":spec["company"],"status":"COMPLETE",
          "new_primitives":np,"new_primitive_count":len(np),"new_failure_classes":nf,"new_failure_class_count":len(nf),
          "cumulative_primitives":len(sp),"cumulative_failure_classes":len(sf)})
    return {"study_id":study["study_id"],"companies_declared":len(study["companies"]),
      "companies_completed":sum(r["status"]=="COMPLETE" for r in rows),"stage_counts":stage_counts,
      "primitive_vocabulary_size":len(sp),"failure_vocabulary_size":len(sf),"rows":rows,
      "interpretation":"Sustained decline in marginal novelty is evidence of a practical ceiling, not proof no unseen form exists."}
def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--study",default="data/eval_study/ma_saturation_pilot_v1.json")
    ap.add_argument("--results",default="data/eval_study/ma_saturation_results"); ap.add_argument("--json",action="store_true"); a=ap.parse_args()
    r=summarize(load(a.study),a.results)
    if a.json: print(json.dumps(r,indent=2)); return
    print(f'Study: {r["study_id"]}\nCompleted: {r["companies_completed"]}/{r["companies_declared"]}')
    print("\n#  Company                              New P  Cum P  New F  Cum F")
    for x in r["rows"]:
        if x["status"]=="MISSING": print(f'{x["order"]:2} {x["company"][:35]:35}   --     --     --     --  MISSING')
        else: print(f'{x["order"]:2} {x["company"][:35]:35} {x["new_primitive_count"]:5} {x["cumulative_primitives"]:6} {x["new_failure_class_count"]:6} {x["cumulative_failure_classes"]:6}')
if __name__=="__main__": main()
