#!/usr/bin/env python3
from __future__ import annotations
import argparse, json, os
from providers.gleif_adapter import GleifJsonAdapter


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="input_path", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--query")
    a = ap.parse_args()
    result = GleifJsonAdapter().from_file(a.input_path, query=a.query).to_dict()
    os.makedirs(os.path.dirname(a.out) or ".", exist_ok=True)
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(f"Wrote GLEIF canonical provider result: {len(result['entities'])} entities, {len(result['relationships'])} relationships -> {a.out}")
    if result.get("warnings"):
        print("Warnings:")
        for w in result["warnings"]:
            print(f"  - {w}")


if __name__ == "__main__":
    main()
