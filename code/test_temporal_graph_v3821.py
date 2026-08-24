#!/usr/bin/env python3
import importlib.util,pathlib
spec=importlib.util.spec_from_file_location("btg",pathlib.Path(__file__).with_name("build_temporal_graph_v3821.py"))
btg=importlib.util.module_from_spec(spec);spec.loader.exec_module(btg)
canonical={"source_company":"Broadcom","source_cik":"x","events":[
 {"event_id":"e1","event_type":"AGREED_TO_ACQUIRE","effective_date":"2022-05-26","parties":{"acquirer":"Broadcom Inc.","target":"VMware, Inc."},"metadata":{}},
 {"event_id":"e2","event_type":"ACQUIRED","effective_date":"2023-11-22","parties":{"acquirer":"Broadcom Inc.","target":"VMware, Inc."},"metadata":{}},
 {"event_id":"e3","event_type":"MERGED_INTO","effective_date":"2023-11-22","parties":{"subject":"Merger Sub","object_entity":"VMware, Inc.","result_entity":"VMware, Inc."},"metadata":{}}
]}
g=btg.build(canonical)
vm=next(n for n in g["nodes"] if n["canonical_name"]=="VMware, Inc.")
assert vm["existence_start"] is None
assert vm["observed_from"]=="2022-05-26"
agreement=next(e for e in g["edges"] if e["edge_type"]=="AGREED_TO_ACQUIRE")
assert agreement["edge_class"]=="EVENT"
assert agreement["end_date"]=="2023-11-22"
own=next(e for e in g["edges"] if e["edge_type"]=="CORPORATE_OWNS")
assert own["edge_class"]=="STATE"
assert own["effective_date"]=="2023-11-22"
print("PASS unknown existence start preserved")
print("PASS observation date separated from existence")
print("PASS agreement closes at acquisition")
print("PASS state vs event edges separated")
print("\n4 passed / 0 failed")
