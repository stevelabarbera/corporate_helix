#!/usr/bin/env python3
import argparse, json, os
from resolution.resolver import resolve_provider_results

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="inputs", action="append", required=True,
                    help="Normalized provider JSON; repeat --in for multiple providers/files")
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    results = []
    for path in args.inputs:
        with open(path, "r", encoding="utf-8") as f:
            results.append(json.load(f))

    graph = resolve_provider_results(results)

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(graph, f, indent=2, ensure_ascii=False)

    s = graph["summary"]
    print(
        f"Wrote resolved graph: {s['node_count']} nodes, "
        f"{s['relationship_count']} relationships, "
        f"{s['merge_count']} merge(s), "
        f"{s['review_candidate_count']} review candidate(s) -> {args.out}"
    )

if __name__ == "__main__":
    main()
