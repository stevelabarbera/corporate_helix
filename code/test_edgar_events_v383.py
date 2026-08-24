#!/usr/bin/env python3
import importlib.util,pathlib
p=pathlib.Path(__file__).with_name("fetch_edgar_events_v383.py")
spec=importlib.util.spec_from_file_location("fe",p)
fe=importlib.util.module_from_spec(spec);spec.loader.exec_module(fe)

# Broadcom-style agreement
b_ag={"item":"1.01","text":"Broadcom Inc. entered into an Agreement and Plan of Merger with VMware, Inc. (VMware)."}
ev=fe.infer(b_ag,"2022-05-26","A","URL")
assert any(e["event_type"]=="AGREED_TO_ACQUIRE" for e in ev),ev
print("PASS generic Broadcom-style agreement")

# Cisco/Splunk-style agreement
c_ag={"item":"1.01","text":"Cisco Systems, Inc. entered into an Agreement and Plan of Merger with Splunk Inc. (Splunk) and Spirit Merger Corp."}
ev=fe.infer(c_ag,"2023-09-20","B","URL")
assert any(e["event_type"]=="AGREED_TO_ACQUIRE" for e in ev),ev
print("PASS generic Cisco/Splunk-style agreement")

# Financing suppression
fin={"item":"1.01","text":"Cisco Systems, Inc. entered into a Credit Agreement with lenders to finance the pending acquisition of Splunk Inc. The merger agreement was previously signed."}
assert fe.infer(fin,"2023-10-01","C","URL")==[]
print("PASS financing suppression")

# Cisco/Splunk closing lineage
close={"item":"2.01","text":"""
Cisco Systems, Inc. completed its acquisition of Splunk Inc.
Spirit Merger Corp. merged with and into Splunk Inc., with Splunk Inc. continuing as the surviving corporation and becoming a wholly owned subsidiary of Cisco Systems, Inc.
"""}
ev=fe.infer(close,"2024-03-18","D","URL")
types=[e["event_type"] for e in ev]
assert "ACQUIRED" in types,types
assert "MERGED_INTO" in types,types
assert "SUBSIDIARY_OF" in types,types
print("PASS generic closing lineage")

# Broadcom conversion extraction remains supported
conv={"item":"2.01","text":"""
Broadcom Inc. completed its acquisition of VMware, Inc.
Merger Sub 1 merged with and into VMware, Inc., with VMware, Inc. continuing as the surviving corporation.
The surviving company was converted from a Delaware corporation into a Delaware limited liability company.
"""}
ev=fe.infer(conv,"2023-11-22","E","URL")
types=[e["event_type"] for e in ev]
assert "CONVERTED_TO" in types,types
print("PASS generic conversion extraction")

print("\n5 passed / 0 failed")
