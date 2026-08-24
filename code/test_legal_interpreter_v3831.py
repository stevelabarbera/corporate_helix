#!/usr/bin/env python3
from legal_nlp.transaction_interpreter import aliases,agreement,completion,mergers,subsidiaries,conversions
c='Cisco Systems, Inc. (“ Cisco ” or the “ Company ”), entered into an Agreement and Plan of Merger (the “ Merger Agreement ”), by and among the Company, Splunk Inc., a Delaware corporation (“ Splunk ”), and Spirit Merger Corp., a Delaware corporation and wholly owned subsidiary of the Company (“ Merger Sub ”), pursuant to which Merger Sub will merge with and into Splunk, with Splunk surviving the Merger as a wholly owned subsidiary of the Company.'
a=aliases(c);assert a['company']=='Cisco Systems, Inc.' and a['splunk']=='Splunk Inc.' and a['merger sub']=='Spirit Merger Corp.',a
print('PASS alias/coreference table')
x=agreement(c);assert x['acquirer']=='Cisco Systems, Inc.' and x['target']=='Splunk Inc.',x
print('PASS agreement role inference')
cc='Cisco Systems, Inc., a Delaware corporation (the “ Company ”), completed the previously announced transaction with Splunk Inc., a Delaware corporation (“ Splunk ”), and Spirit Merger Corp., a Delaware corporation and wholly owned subsidiary of the Company (“ Merger Sub ”). Pursuant to the Merger Agreement, Merger Sub merged with and into Splunk, with Splunk surviving the Merger as a wholly owned subsidiary of the Company.'
x=completion(cc);assert x['target']=='Splunk Inc.',x
m=mergers(cc);assert m and m[0]['subject']=='Spirit Merger Corp.' and m[0]['object_entity']=='Splunk Inc.',m
s=subsidiaries(cc);assert s and s[0]['subject']=='Splunk Inc.' and s[0]['object_entity']=='Cisco Systems, Inc.',s
print('PASS Cisco completion + lineage')
b='Broadcom Inc., a Delaware corporation (the “Company” or “Broadcom”), entered into an Agreement and Plan of Merger (the “Merger Agreement”) with VMware, Inc. (“VMware”), a Delaware corporation.'
x=agreement(b);assert x['acquirer']=='Broadcom Inc.' and x['target']=='VMware, Inc.',x
print('PASS Broadcom agreement regression')
bc='Broadcom Inc. (“Broadcom”) completed its acquisition of VMware, Inc. (“VMware”). The Surviving Company was converted from a Delaware corporation into a Delaware limited liability company.'
x=completion(bc);assert x['target']=='VMware, Inc.',x
v=conversions(bc,'VMware, Inc.');assert v and v[0]['subject']=='VMware, Inc.',v
print('PASS Broadcom completion + conversion')
print('\n5 passed / 0 failed')
