#!/usr/bin/env python3
import importlib.util,pathlib
p=pathlib.Path(__file__).with_name("benchmark_m384_temporal_events.py")
spec=importlib.util.spec_from_file_location("m",p);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)

aliases={"Broadcom":"Broadcom Inc.","Company":"Broadcom Inc.","VMware":"VMware, Inc.",
         "Merger Sub 1":"Verona Merger Sub, Inc.","Holdco":"Verona Holdco, Inc."}
orgs=list(set(aliases.values()))

agreement="""Broadcom Inc. entered into an Agreement and Plan of Merger with VMware, Inc. The Merger Agreement provides that Merger Sub 1 will be merged with and into VMware, with VMware continuing as the surviving corporation and becoming a wholly owned subsidiary of Holdco. The Surviving Company will be converted from a Delaware corporation into a Delaware limited liability company."""
ev=m.infer_events(agreement,aliases,orgs,"1.01")
assert any(x["event_type"]=="AGREED_TO_ACQUIRE" and x["status"]=="COMPLETED" for x in ev),ev
assert any(x["event_type"]=="MERGED_INTO" and x["status"]=="PROPOSED" for x in ev),ev
assert any(x["event_type"]=="CONVERTED_TO" and x["status"]=="PROPOSED" for x in ev),ev
assert not any(x["event_type"]=="MERGED_INTO" for x in m.completed_only(ev))
print("PASS agreement mechanics remain proposed")

closing="""Broadcom Inc. completed its acquisition of VMware, Inc. Merger Sub 1 merged with and into VMware, with VMware continuing as the surviving corporation and becoming a wholly owned subsidiary of Holdco. The Surviving Company was converted from a Delaware corporation into a Delaware limited liability company."""
ev=m.infer_events(closing,aliases,orgs,"2.01")
assert any(x["event_type"]=="ACQUIRED" and x["status"]=="COMPLETED" for x in ev),ev
assert any(x["event_type"]=="MERGED_INTO" and x["status"]=="COMPLETED" for x in ev),ev
assert any(x["event_type"]=="CONVERTED_TO" and x["status"]=="COMPLETED" for x in ev),ev
print("PASS closing mechanics become completed")

neg="""Cisco Systems, Inc. issued Senior Notes under an underwriting agreement to finance the proposed acquisition of Splunk Inc."""
assert m.infer_events(neg,{},[],"1.01")==[]
print("PASS financing negative suppressed")

print("\n3 passed / 0 failed")
