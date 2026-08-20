#!/usr/bin/env python3
import argparse, json, os
from normalization.pipeline import normalize_provider_result
def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--in",dest="input_path",required=True)
    ap.add_argument("--out",required=True)
    a=ap.parse_args()
    with open(a.input_path,"r",encoding="utf-8") as f: raw=json.load(f)
    norm=normalize_provider_result(raw)
    os.makedirs(os.path.dirname(a.out) or ".",exist_ok=True)
    with open(a.out,"w",encoding="utf-8") as f: json.dump(norm,f,indent=2,ensure_ascii=False)
    print(f"Wrote normalized result: {norm['normalization']['entity_count']} entities, {norm['normalization']['relationship_count']} relationships, {len(norm['normalization']['duplicate_groups'])} duplicate group(s) -> {a.out}")
if __name__=="__main__": main()
