#!/usr/bin/env python3
import importlib.util,pathlib
p=pathlib.Path(__file__).with_name("benchmark_m385_merger_coref.py")
spec=importlib.util.spec_from_file_location("m",p)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

aliases={
 "Broadcom":"Broadcom Inc.","VMware":"VMware, Inc.",
 "Holdco":"Verona Holdco, Inc.","Merger Sub 1":"Verona Merger Sub, Inc.",
 "Merger Sub 2":"Barcelona Merger Sub 2, Inc.",
 "Merger Sub 3":"Barcelona Merger Sub 3, LLC"
}
orgs=sorted(set(aliases.values()))

text="""Merger Sub 1 merged with and into VMware (the "First Merger"), with VMware continuing as the surviving corporation in the First Merger (the "Surviving Company") and becoming a wholly owned subsidiary of Holdco; following the Conversion, Merger Sub 2 merged with and into Holdco (the "Second Merger"), with Holdco continuing as the surviving corporation in the Second Merger (the "Holdco Surviving Company") and becoming a wholly owned subsidiary of Broadcom; and following the Second Merger, the Holdco Surviving Company merged with and into Merger Sub 3, with Merger Sub 3 continuing as the surviving limited liability company and as a wholly owned subsidiary of Broadcom."""

a=m.enrich_survivor_aliases(text,aliases)
assert a["Surviving Company"]=="VMware, Inc.",a
assert a["Holdco Surviving Company"]=="Verona Holdco, Inc.",a
print("PASS surviving-entity coreference")

ev=m.infer_events(text,aliases,orgs,"2.01")
third=[e for e in ev if e["event_type"]=="MERGED_INTO"
       and e["subject"]=="Verona Holdco, Inc."
       and e["object"]=="Barcelona Merger Sub 3, LLC"]
assert third,ev
print("PASS third-merger lineage extraction")

final=m.completed_only(ev)
assert not any(e["event_type"]=="SUBSIDIARY_OF"
               and e["subject"]=="Verona Holdco, Inc." for e in final),final
print("PASS transient subsidiary state suppressed from final graph")

agreement="""Broadcom entered into an Agreement and Plan of Merger with VMware. Merger Sub 1 will be merged with and into VMware, with VMware continuing as the surviving corporation (the "Surviving Company")."""
ev=m.infer_events(agreement,aliases,orgs,"1.01")
assert any(e["event_type"]=="MERGED_INTO" and e["status"]=="PROPOSED" for e in ev),ev
assert not any(e["event_type"]=="MERGED_INTO" for e in m.completed_only(ev)),ev
print("PASS proposed mechanics remain non-mutating")

neg="Broadcom entered into a Credit Agreement to finance the proposed acquisition of VMware."
assert m.infer_events(neg,aliases,orgs,"1.01")==[]
print("PASS financing suppression regression")

print("\n5 passed / 0 failed")
