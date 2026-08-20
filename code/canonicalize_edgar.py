#!/usr/bin/env python3
import argparse, json
from providers.edgar_adapter import EdgarJsonAdapter

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--in", dest="input_path", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--query")
    a=ap.parse_args()
    result=EdgarJsonAdapter().from_file(a.input_path, query=a.query)
    with open(a.out,"w",encoding="utf-8") as f:
        json.dump(result.to_dict(),f,indent=2,ensure_ascii=False)
    print(f"Wrote canonical EDGAR result: {len(result.entities)} entities, {len(result.relationships)} relationships -> {a.out}")
    for w in result.warnings: print("WARNING:",w)
if __name__=="__main__": main()
