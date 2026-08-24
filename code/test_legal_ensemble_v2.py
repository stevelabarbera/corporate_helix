#!/usr/bin/env python3
import importlib.util,pathlib
p=pathlib.Path(__file__).with_name("benchmark_legal_ensemble_v2.py")
spec=importlib.util.spec_from_file_location("ens",p);ens=importlib.util.module_from_spec(spec);spec.loader.exec_module(ens)
outputs={
 "regex":{"orgs":["Cisco Systems, Inc.","Section 262 of the General Corporation"],"aliases":{"Company":"Cisco Systems, Inc."}},
 "spacy":{"orgs":["Cisco Systems, Inc.","Splunk Inc.","Section 262 of the General Corporation"],"aliases":{"Company":"Cisco Systems, Inc.","Splunk":"Splunk Inc."}},
 "legal_rules":{"orgs":["Cisco Systems, Inc.","Splunk Inc."],"aliases":{"Company":"Cisco Systems, Inc.","Splunk":"Splunk Inc."}}
}
weights={"regex":0.5,"spacy":1.0,"legal_rules":1.25}
x=ens.fuse(outputs,weights,1.5)
assert "Cisco Systems, Inc." in x["orgs"]
assert "Splunk Inc." in x["orgs"]
assert not any("Section 262" in o for o in x["orgs"])
assert x["aliases"]["Company"]=="Cisco Systems, Inc."
assert x["aliases"]["Splunk"]=="Splunk Inc."
print("PASS weighted organization fusion")
print("PASS statutory false-positive rejection")
print("PASS alias vote fusion")
neg="Cisco Systems, Inc. issued Senior Notes to finance the proposed acquisition of Splunk Inc."
assert ens.infer_events(neg,x["aliases"],x["orgs"])==[]
print("PASS financing negative gate")
pos="Cisco Systems, Inc. completed the previously announced transaction with Splunk Inc."
ev=ens.infer_events(pos,x["aliases"],x["orgs"])
assert ev and ev[0]["event_type"]=="ACQUIRED",ev
print("PASS positive acquisition event")
print("\n5 passed / 0 failed")
