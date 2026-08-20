#!/usr/bin/env python3
import argparse,json,os
from adjudication.engine import evaluate_candidate
from adjudication.evidence_packet import build_evidence_packet

def append_jsonl(path,obj):
    os.makedirs(os.path.dirname(path) or ".",exist_ok=True)
    with open(path,"a",encoding="utf-8") as f:
        f.write(json.dumps(obj,ensure_ascii=False)+"\n")

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--graph",required=True)
    ap.add_argument("--policy",default="SAME_ENTITY",choices=["SAME_ENTITY","SUBSIDIARY_OF"])
    ap.add_argument("--pending",default="./data/review/pending.jsonl")
    ap.add_argument("--all-decisions",action="store_true",
                    help="Queue ACCEPT/REJECT too. Default queues REVIEW only.")
    args=ap.parse_args()

    with open(args.graph,"r",encoding="utf-8") as f:
        graph=json.load(f)
    nodes={n["node_id"]:n for n in graph.get("nodes",[])}

    packets=[]
    for c in graph.get("review_candidates") or []:
        left=nodes[c["left_node_id"]]
        right=nodes[c["right_node_id"]]
        ev=evaluate_candidate(graph,left,right,args.policy)

        # Compatibility with M3.5 v2 engine, which may not include policy in the result.
        ev.setdefault("policy", args.policy)

        if not args.all_decisions and ev["decision"]!="REVIEW":
            continue

        packet=build_evidence_packet(
            graph,left,right,ev,policy_name=args.policy
        )
        packet["candidate_source"]=c.get("reason","review_candidate")
        packets.append(packet)

    existing=set()
    if os.path.exists(args.pending):
        with open(args.pending,"r",encoding="utf-8") as f:
            for line in f:
                try:
                    existing.add(json.loads(line)["packet_id"])
                except Exception:
                    pass

    added=0
    for p in packets:
        if p["packet_id"] not in existing:
            append_jsonl(args.pending,p)
            existing.add(p["packet_id"])
            added+=1

    print(f"Review queue: {len(packets)} eligible packet(s), {added} added -> {args.pending}")

if __name__=="__main__":
    main()
