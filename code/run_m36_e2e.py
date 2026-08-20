#!/usr/bin/env python3
import argparse, os, subprocess, sys

def run(cmd):
    print("+"," ".join(cmd))
    subprocess.run(cmd,check=True)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--model")
    ap.add_argument("--fixture",default="./data/processed/resolved_review_fixture.json")
    ap.add_argument("--pending",default="./data/review/e2e_pending.jsonl")
    args=ap.parse_args()

    if os.path.exists(args.pending):
        os.remove(args.pending)

    run([sys.executable,"./code/create_review_fixture.py","--out",args.fixture])
    run([
        sys.executable,"./code/build_review_queue.py",
        "--graph",args.fixture,
        "--policy","SAME_ENTITY",
        "--pending",args.pending
    ])
    run([
        sys.executable,"./code/show_review_queue.py",
        "--pending",args.pending
    ])

    if args.model:
        run([
            sys.executable,"./code/ollama_adjudicate.py",
            "--pending",args.pending,
            "--model",args.model,
            "--out","./data/review/e2e_llm_adjudicated.jsonl"
        ])
    else:
        print("\nDeterministic end-to-end path complete.")
        print("To include Ollama, rerun with: --model <installed-model-name>")

if __name__=="__main__":
    main()
