#!/usr/bin/env python3
import importlib.util, pathlib

p=pathlib.Path(__file__).with_name("fetch_edgar_events_v3811.py")
spec=importlib.util.spec_from_file_location("fe",p)
fe=importlib.util.module_from_spec(spec);spec.loader.exec_module(fe)

# 1. Realistic SEC HTML normalization + Item detection.
html = """
<html><body>
<div><b>Item 1.01</b></div>
<p>Entry into a Material Definitive Agreement.</p>
<p>Broadcom Inc. entered into an Agreement and Plan of Merger with VMware, Inc. on May 26, 2022.</p>
<div><b>Item 8.01</b></div>
<p>Other Events.</p>
</body></html>
"""
text=fe.strip_html(html)
sections=fe.item_sections(text)
assert len(sections)==1,(text,sections)
assert sections[0]["item"]=="1.01",sections
print("PASS SEC HTML item detection")

# 2. True agreement.
ev=fe.infer(sections[0],"2022-05-26","A","URL")
assert [e["event_type"] for e in ev]==["AGREED_TO_ACQUIRE"],ev
print("PASS true agreement")

# 3. Financing suppression.
financing={"item":"1.01","text":"""
Item 1.01 Entry into Definitive Material Agreement.
Broadcom Inc. entered into a Credit Agreement with lenders in connection with
Broadcom's pending acquisition of VMware, Inc. The term loan will finance the
acquisition. The Merger Agreement is dated May 26, 2022.
"""}
ev=fe.infer(financing,"2023-08-16","B","URL")
assert ev==[],ev
print("PASS financing suppression")

# 4. Closing + lineage.
closing={"item":"2.01","text":"""
Item 2.01 Completion of Acquisition or Disposition of Assets.
Broadcom Inc. completed its acquisition of VMware, Inc.
Merger Sub 1 merged with and into VMware, with VMware continuing as the surviving corporation.
The Surviving Company was converted from a Delaware corporation into a Delaware limited liability company.
Merger Sub 2 merged with and into Holdco, with Holdco continuing as the surviving corporation.
The Holdco Surviving Company merged with and into Merger Sub 3, with Merger Sub 3 continuing as the surviving limited liability company and as a wholly owned subsidiary of Broadcom.
"""}
ev=fe.infer(closing,"2023-11-22","C","URL")
types=[e["event_type"] for e in ev]
assert types==["ACQUIRED","MERGED_INTO","CONVERTED_TO","MERGED_INTO","MERGED_INTO","SUBSIDIARY_OF"],types
print("PASS closing lineage extraction")

conv=[e for e in ev if e["event_type"]=="CONVERTED_TO"][0]
assert conv["result_entity"] is None,conv
assert conv["metadata"]["do_not_infer_result_name"] is True,conv
print("PASS conversion name not invented")

print("\n5 passed / 0 failed")
