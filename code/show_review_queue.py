#!/usr/bin/env python3
import argparse,json,os

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--pending",default="./data/review/pending.jsonl")
    args=ap.parse_args()
    if not os.path.exists(args.pending):
        print("0 pending review packet(s)")
        return
    count=0
    with open(args.pending,"r",encoding="utf-8") as f:
        for line in f:
            if not line.strip(): continue
            p=json.loads(line); count+=1
            a=p["candidate_a"]; b=p["candidate_b"]; d=p["deterministic_evaluation"]
            print(f"{p['packet_id']} | {p['policy']} | {a['canonical_name']} <-> {b['canonical_name']} | {d['decision']} {d['resolution_reason']}")
    print(f"\n{count} pending review packet(s)")
if __name__=="__main__": main()
