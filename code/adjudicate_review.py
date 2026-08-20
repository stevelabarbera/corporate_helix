#!/usr/bin/env python3
import argparse,json,os
from datetime import datetime,timezone

VALID={"CONFIRMED","STRONG","POSSIBLE","AMBIGUOUS","CONFLICT","UNRELATED"}

def load_jsonl(path):
    rows=[]
    if not os.path.exists(path): return rows
    with open(path,"r",encoding="utf-8") as f:
        for line in f:
            if line.strip(): rows.append(json.loads(line))
    return rows

def write_jsonl(path,rows):
    os.makedirs(os.path.dirname(path) or ".",exist_ok=True)
    with open(path,"w",encoding="utf-8") as f:
        for r in rows: f.write(json.dumps(r,ensure_ascii=False)+"\n")

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--packet-id",required=True)
    ap.add_argument("--decision",required=True,choices=sorted(VALID))
    ap.add_argument("--rationale",required=True)
    ap.add_argument("--reviewer",default="human")
    ap.add_argument("--pending",default="./data/review/pending.jsonl")
    ap.add_argument("--adjudicated",default="./data/review/adjudicated.jsonl")
    args=ap.parse_args()

    pending=load_jsonl(args.pending)
    found=None; remaining=[]
    for p in pending:
        if p.get("packet_id")==args.packet_id and found is None:
            found=p
        else:
            remaining.append(p)
    if found is None:
        raise SystemExit(f"Packet not found: {args.packet_id}")

    found["adjudication"]["human"]={
        "decision":args.decision,
        "rationale":args.rationale,
        "reviewer":args.reviewer,
        "reviewed_at":datetime.now(timezone.utc).isoformat(),
    }
    found["adjudication"]["final"]=found["adjudication"]["human"]
    found["adjudication"]["status"]="ADJUDICATED"

    write_jsonl(args.pending,remaining)
    existing=load_jsonl(args.adjudicated)
    existing.append(found)
    write_jsonl(args.adjudicated,existing)
    print(f"Adjudicated {args.packet_id}: {args.decision}")

if __name__=="__main__":
    main()
