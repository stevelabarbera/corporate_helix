#!/usr/bin/env python3
import argparse,json,os
from adjudication.engine import evaluate_candidate
from adjudication.evidence_packet import build_evidence_packet

def load(path):
    with open(path,encoding="utf-8") as f:return json.load(f)

def build_graph(case):
    return {"nodes":[case["left"],case["right"]],
            "relationships":list(case.get("relationships") or []),
            "review_candidates":[{"left_node_id":case["left"]["node_id"],
                                  "right_node_id":case["right"]["node_id"],
                                  "reason":"evaluation_fixture"}]}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--cases",default="./data/eval/cases.json")
    ap.add_argument("--out",default="./data/eval/deterministic_results.json")
    ap.add_argument("--packets",default="./data/eval/eval_packets.jsonl")
    a=ap.parse_args()
    cases=load(a.cases);results=[];packets=[]
    for case in cases:
        g=build_graph(case)
        ev=evaluate_candidate(g,case["left"],case["right"],case["expected_policy"])
        ev.setdefault("policy",case["expected_policy"])
        packet=build_evidence_packet(g,case["left"],case["right"],ev,policy_name=case["expected_policy"])
        packet["case_id"]=case["case_id"];packet["expected_llm"]=case["expected_llm"];packet["expected_deterministic"]=case["expected_deterministic"]
        packets.append(packet)
        ok=ev["decision"]==case["expected_deterministic"]
        results.append({"case_id":case["case_id"],"expected":case["expected_deterministic"],"actual":ev["decision"],
                        "resolution_reason":ev.get("resolution_reason"),"score":ev.get("score"),"pass":ok})
        print(("PASS" if ok else "FAIL"),case["case_id"],"->",ev["decision"],ev.get("resolution_reason"),"score",ev.get("score"))
    os.makedirs(os.path.dirname(a.out) or ".",exist_ok=True)
    with open(a.out,"w",encoding="utf-8") as f:json.dump(results,f,indent=2)
    with open(a.packets,"w",encoding="utf-8") as f:
        for p in packets:f.write(json.dumps(p,ensure_ascii=False)+"\n")
    passed=sum(r["pass"] for r in results)
    print(f"\nDeterministic corpus: {passed} passed / {len(results)-passed} failed")
if __name__=="__main__":main()
