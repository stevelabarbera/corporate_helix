#!/usr/bin/env python3
import argparse, json, importlib.util, pathlib, sys

def load_m385():
    p=pathlib.Path(__file__).with_name("benchmark_m385_merger_coref.py")
    spec=importlib.util.spec_from_file_location("m385",p)
    m=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--inputs",nargs="+",required=True)
    ap.add_argument("--spacy-model",default="en_core_web_sm")
    ap.add_argument("--threshold",type=float,default=1.5)
    ap.add_argument("--json-out",required=True)
    a=ap.parse_args()

    m=load_m385()
    try:
        sp=m.SpacyBackend(a.spacy_model)
    except Exception as e:
        print("BACKEND_UNAVAILABLE:",e)
        sys.exit(3)

    backends=[m.RegexBackend(),sp,m.LegalRulesBackend()]
    weights={"regex":0.5,"spacy":1.0,"legal_rules":1.25}
    output={"schema_version":"m3.8.5-cold-run-v1","filings":[]}

    for path in a.inputs:
        raw=json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
        for f in raw.get("filings",[]):
            fr={"source_file":path,"company":raw.get("company"),"cik":raw.get("cik"),
                "filing_date":f.get("filing_date"),"accession":f.get("accession"),
                "form":f.get("form"),"items":f.get("items"),"sections":[]}
            for s in f.get("sections",[]):
                text=s.get("text","")
                outs={b.name:b.parse(text) for b in backends}
                fused=m.fuse(outs,weights,a.threshold)
                raw_events=m.infer_events(text,fused["aliases"],fused["orgs"],s.get("item"))
                completed=m.completed_only(raw_events)
                proposed=[e for e in raw_events if e.get("status")=="PROPOSED"]
                fr["sections"].append({"item":s.get("item"),"orgs":fused["orgs"],
                    "aliases":fused["aliases"],"raw_events":raw_events,
                    "completed_events":completed,"proposed_events":proposed,
                    "org_votes":fused.get("org_votes",{})})
                print(f"{f.get('filing_date')} {f.get('accession')} Item {s.get('item')} -> "
                      f"{len(fused['orgs'])} org(s), {len(fused['aliases'])} alias(es), "
                      f"{len(completed)} completed, {len(proposed)} proposed")
                for e in completed:
                    print(f"  COMPLETED {e['event_type']}: {e['subject']} -> {e['object']}")
                for e in proposed:
                    print(f"  PROPOSED  {e['event_type']}: {e['subject']} -> {e['object']}")
            output["filings"].append(fr)

    pathlib.Path(a.json_out).parent.mkdir(parents=True,exist_ok=True)
    pathlib.Path(a.json_out).write_text(json.dumps(output,indent=2,ensure_ascii=False),encoding="utf-8")
    print(f"Wrote cold-run output -> {a.json_out}")

if __name__=="__main__":
    main()
