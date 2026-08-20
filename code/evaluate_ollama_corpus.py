#!/usr/bin/env python3
import argparse,json,os,importlib.util,pathlib
spec=importlib.util.spec_from_file_location("oa",pathlib.Path(__file__).with_name("ollama_adjudicate.py"))
oa=importlib.util.module_from_spec(spec);spec.loader.exec_module(oa)
def load_jsonl(path):
    if not os.path.exists(path):return []
    with open(path,encoding="utf-8") as f:return [json.loads(x) for x in f if x.strip()]
def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--packets",default="./data/eval/eval_packets.jsonl")
    ap.add_argument("--model",required=True)
    ap.add_argument("--url",default="http://localhost:11434/api/chat")
    ap.add_argument("--out",default="./data/eval/ollama_results.json")
    a=ap.parse_args()
    packets=load_jsonl(a.packets);rows=[]
    for i,p in enumerate(packets,1):
        try:
            result=oa.call(p,a.model,a.url)
            errs=oa.consistency_errors(result,p)
            valid=not errs
            expected=p["expected_llm"]
            semantic_match=result.get("decision")==expected
            row={"case_id":p["case_id"],"expected":expected,"actual":result.get("decision"),
                 "confidence":result.get("confidence"),"validation_status":"VALID" if valid else "INVALID",
                 "validation_errors":errs,"semantic_match":semantic_match,
                 "pass":valid and semantic_match,"rationale":result.get("rationale")}
        except Exception as e:
            row={"case_id":p["case_id"],"expected":p["expected_llm"],"actual":None,"confidence":None,
                 "validation_status":"ERROR","validation_errors":[repr(e)],"semantic_match":False,
                 "pass":False,"rationale":None}
        rows.append(row)
        print(f"[{i}/{len(packets)}]",("PASS" if row["pass"] else "FAIL"),row["case_id"],
              "expected",row["expected"],"got",row["actual"],row["validation_status"])
    with open(a.out,"w",encoding="utf-8") as f:json.dump(rows,f,indent=2)
    passed=sum(r["pass"] for r in rows);valid=sum(r["validation_status"]=="VALID" for r in rows)
    print(f"\nOllama corpus: {passed} passed / {len(rows)-passed} failed")
    print(f"Validator: {valid} valid / {len(rows)-valid} invalid-or-error")
if __name__=="__main__":main()
