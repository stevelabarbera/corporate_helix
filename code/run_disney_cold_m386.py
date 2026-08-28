#!/usr/bin/env python3
import argparse,importlib.util,json,time
from pathlib import Path
ap=argparse.ArgumentParser(); ap.add_argument("--input",default="./data/raw/edgar_disney_fox_cold_m386.json")
ap.add_argument("--parser",default="./code/benchmark_m385_merger_coref.py"); ap.add_argument("--spacy-model",default="en_core_web_sm")
ap.add_argument("--out",default="./data/benchmark/results_disney_cold_m386.json"); a=ap.parse_args()
spec=importlib.util.spec_from_file_location("m",a.parser); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
sp=m.SpacyBackend(a.spacy_model); backends=[m.RegexBackend(),sp,m.LegalRulesBackend()]
raw=json.loads(Path(a.input).read_text()); results=[]; start=time.perf_counter()
for f in raw["filings"]:
 sec=f["sections"][0]; outputs={b.name:b.parse(sec["text"]) for b in backends}
 fused=m.fuse(outputs,{"regex":.5,"spacy":1.0,"legal_rules":1.25},1.5)
 ev=m.infer_events(sec["text"],fused["aliases"],fused["orgs"],sec["item"]); final=m.completed_only(ev)
 row={"case":f["cold_case_id"],"accession":f["accession"],"orgs":fused["orgs"],"aliases":fused["aliases"],
      "raw_events":ev,"completed_events":final}; results.append(row)
 print(f"\n=== {row['case']} ===\nORG={len(row['orgs'])} aliases={len(row['aliases'])} raw={len(ev)} completed={len(final)}")
 print("Organizations:"); [print(" -",x) for x in row["orgs"]]
 print("Aliases:"); [print(f" - {k} -> {v}") for k,v in sorted(row["aliases"].items())]
 print("Events:")
 if not ev: print(" - NONE")
 for e in ev: print(f" - {e['event_type']} / {e['status']} / {e.get('lifecycle','FINAL')}: {e['subject']} -> {e['object']}")
Path(a.out).parent.mkdir(parents=True,exist_ok=True)
Path(a.out).write_text(json.dumps({"parser":"FROZEN_M3.8.5","elapsed_seconds":time.perf_counter()-start,"cases":results},indent=2))
print(f"\nFrozen cold results -> {a.out}\nIMPORTANT: preserve this file before any Disney-specific tuning.")
