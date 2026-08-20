#!/usr/bin/env python3
import argparse,json,os
from adjudication.engine import evaluate_candidate

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--graph",required=True)
    ap.add_argument("--policy",required=True,choices=["SAME_ENTITY","SUBSIDIARY_OF"])
    ap.add_argument("--out",required=True)
    ap.add_argument("--left-node")
    ap.add_argument("--right-node")
    a=ap.parse_args()
    with open(a.graph,"r",encoding="utf-8") as f:g=json.load(f)
    nm={n["node_id"]:n for n in g.get("nodes",[])}
    pairs=[]
    if a.left_node and a.right_node:
        pairs=[(nm[a.left_node],nm[a.right_node],"manual")]
    else:
        for c in g.get("review_candidates",[]):
            pairs.append((nm[c["left_node_id"]],nm[c["right_node_id"]],c.get("reason","review_candidate")))
    results=[]
    for l,r,src in pairs:
        x=evaluate_candidate(g,l,r,a.policy);x["candidate_source"]=src;results.append(x)
    out={"m35_version":"m3.5-v1","source_graph":a.graph,"policy":a.policy,"results":results,
         "summary":{"candidate_count":len(results),
                    "accept_count":sum(x["decision"]=="ACCEPT" for x in results),
                    "review_count":sum(x["decision"]=="REVIEW" for x in results),
                    "reject_count":sum(x["decision"]=="REJECT" for x in results)}}
    os.makedirs(os.path.dirname(a.out) or ".",exist_ok=True)
    with open(a.out,"w",encoding="utf-8") as f:json.dump(out,f,indent=2,ensure_ascii=False)
    s=out["summary"]
    print(f"Wrote M3.5 evaluation: {s['candidate_count']} candidate(s), {s['accept_count']} accept, {s['review_count']} review, {s['reject_count']} reject -> {a.out}")
if __name__=="__main__":main()
