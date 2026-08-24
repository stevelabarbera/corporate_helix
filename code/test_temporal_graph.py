#!/usr/bin/env python3
import importlib.util, pathlib

spec=importlib.util.spec_from_file_location("btg",pathlib.Path(__file__).with_name("build_temporal_graph.py"))
btg=importlib.util.module_from_spec(spec);spec.loader.exec_module(btg)

canonical={
 "source_company":"Broadcom","source_cik":"0001730168",
 "events":[
  {"event_id":"e1","event_type":"AGREED_TO_ACQUIRE","effective_date":"2022-05-26",
   "parties":{"acquirer":"Broadcom Inc.","target":"VMware, Inc."},"metadata":{}},
  {"event_id":"e2","event_type":"ACQUIRED","effective_date":"2023-11-22",
   "parties":{"acquirer":"Broadcom Inc.","target":"VMware, Inc."},"metadata":{}},
  {"event_id":"e3","event_type":"MERGED_INTO","effective_date":"2023-11-22",
   "parties":{"subject":"Verona Merger Sub, Inc.","object_entity":"VMware, Inc.","result_entity":"VMware, Inc."},
   "metadata":{"step":"First Merger"}},
  {"event_id":"e4","event_type":"CONVERTED_TO","effective_date":"2023-11-22",
   "parties":{"subject":"VMware, Inc.","result_entity":None},
   "metadata":{"from_legal_form":"Delaware corporation","to_legal_form":"Delaware limited liability company","result_name_explicitly_stated":False}},
  {"event_id":"e5","event_type":"SUBSIDIARY_OF","effective_date":"2023-11-22",
   "parties":{"subject":"Barcelona Merger Sub 3, LLC","object_entity":"Broadcom Inc."},"metadata":{}}
 ]
}
g=btg.build(canonical)
assert g["summary"]["event_count"]==5,g["summary"]
assert any(e["edge_type"]=="AGREED_TO_ACQUIRE" for e in g["edges"])
assert any(e["edge_type"]=="ACQUIRED" for e in g["edges"])
assert any(e["edge_type"]=="CORPORATE_OWNS" and e["metadata"].get("derived_from")=="ACQUIRED" for e in g["edges"])
vm=next(n for n in g["nodes"] if n["canonical_name"]=="VMware, Inc.")
assert any(s["state_type"]=="LEGAL_FORM" for s in vm["states"]),vm
ms=next(n for n in g["nodes"] if n["canonical_name"]=="Verona Merger Sub, Inc.")
assert ms["last_seen"]=="2023-11-22",ms
print("PASS event ingestion")
print("PASS acquisition edge derivation")
print("PASS conversion state")
print("PASS merged-out lifecycle")
print("\n4 passed / 0 failed")
