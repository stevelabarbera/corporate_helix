#!/usr/bin/env python3
from legal_nlp.transaction_interpreter import alias_map, agreement, completion, merger_actions, subsidiary_actions, conversion_actions

cisco_ag = """On September 20, 2023, Cisco Systems, Inc. (“ Cisco ” or the “ Company ”), entered into an Agreement and Plan of Merger (the “ Merger Agreement ”), by and among the Company, Splunk Inc., a Delaware corporation (“ Splunk ”), and Spirit Merger Corp., a Delaware corporation and wholly owned subsidiary of the Company (“ Merger Sub ”), pursuant to which Merger Sub will merge with and into Splunk, with Splunk surviving the Merger as a wholly owned subsidiary of the Company. Section 262 of the General Corporation Law applies."""
a = alias_map(cisco_ag)
assert a["company"] == "Cisco Systems, Inc.", a
assert a["splunk"] == "Splunk Inc.", a
assert a["merger sub"] == "Spirit Merger Corp.", a
x = agreement(cisco_ag)
assert x["acquirer"] == "Cisco Systems, Inc." and x["target"] == "Splunk Inc.", x
print("PASS Cisco agreement bounded before legal citation noise")

cisco_close = """On March 18, 2024, Cisco Systems, Inc., a Delaware corporation (the “ Company ”), completed the previously announced transaction with Splunk Inc., a Delaware corporation (“ Splunk ”), and Spirit Merger Corp., a Delaware corporation and wholly owned subsidiary of the Company (“ Merger Sub ”), pursuant to the Agreement and Plan of Merger. Pursuant to the Merger Agreement, Merger Sub merged with and into Splunk, with Splunk surviving the Merger as a wholly owned subsidiary of the Company."""
x = completion(cisco_close)
assert x["acquirer"] == "Cisco Systems, Inc." and x["target"] == "Splunk Inc.", x
m = merger_actions(cisco_close)
assert m and m[0]["subject"] == "Spirit Merger Corp." and m[0]["object_entity"] == "Splunk Inc.", m
s = subsidiary_actions(cisco_close)
assert s and s[0]["subject"] == "Splunk Inc." and s[0]["object_entity"] == "Cisco Systems, Inc.", s
print("PASS Cisco completion + lineage")

broad_ag = """Broadcom Inc., a Delaware corporation (the “Company” or “Broadcom”), entered into an Agreement and Plan of Merger (the “Merger Agreement”) with VMware, Inc. (“VMware”), a Delaware corporation."""
x = agreement(broad_ag)
assert x["acquirer"] == "Broadcom Inc." and x["target"] == "VMware, Inc.", x
print("PASS Broadcom agreement regression")

broad_close = """On November 22, 2023, Broadcom Inc. (“Broadcom”) completed its acquisition of VMware, Inc. (“VMware”) pursuant to the Agreement and Plan of Merger. Broadcom funded the Cash Consideration through borrowings under the Credit Agreement. Merger Sub 1 merged with and into VMware, with VMware continuing as the surviving corporation. The Surviving Company was converted from a Delaware corporation into a Delaware limited liability company."""
x = completion(broad_close)
assert x["acquirer"] == "Broadcom Inc." and x["target"] == "VMware, Inc.", x
c = conversion_actions(broad_close, "VMware, Inc.")
assert c and c[0]["subject"] == "VMware, Inc.", c
print("PASS Broadcom closing not suppressed by financing reference")

print("\n4 passed / 0 failed")
