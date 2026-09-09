#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

CODE_DIR = Path(__file__).resolve().parent
if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))

from analysts.llm_analyst import OllamaAnalyst


def main() -> int:
    ap = argparse.ArgumentParser(description="Generate advisory Corporation Helix investigation proposals with a local Ollama model.")
    ap.add_argument("--entity", required=True)
    ap.add_argument("--lei")
    ap.add_argument("--jurisdiction")
    ap.add_argument("--relationship", action="append", default=[])
    ap.add_argument("--model", default="gemma3:1b")
    ap.add_argument("--timeout", type=int, default=300)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--debug", action="store_true", help="Print raw/parsed Ollama response and dropped-item reasons")
    args = ap.parse_args()

    analyst = OllamaAnalyst(model=args.model, timeout=args.timeout)
    decisions = analyst.analyze(
        subject=args.entity,
        subject_identifier=args.lei,
        jurisdiction=args.jurisdiction,
        relationships=args.relationship,
    )

    if args.json:
        payload = {"decisions": [d.to_dict() for d in decisions]}
        if args.debug and analyst.last_debug:
            payload["debug"] = {
                "raw_content": analyst.last_debug.raw_content,
                "parsed_payload": analyst.last_debug.parsed_payload,
                "normalized_items": analyst.last_debug.normalized_items,
                "accepted_count": analyst.last_debug.accepted_count,
                "dropped_items": analyst.last_debug.dropped_items,
            }
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return 0

    print("=" * 72)
    print("CORPORATION HELIX — ADVISORY ANALYST SUGGESTIONS")
    print("=" * 72)
    print(f"Entity : {args.entity}")
    print(f"LEI    : {args.lei or '-'}")
    print(f"Model  : {args.model}")
    print(f"Count  : {len(decisions)}")
    print()
    for d in decisions:
        print(f"[{d.decision_type.value}/{d.confidence}] {d.value or '(abstain)'}")
        print(f"  Reason        : {d.reason or '-'}")
        print(f"  Pivot eligible: {d.pivot_eligible}")
        print("  Trust         : ADVISORY_ONLY — deterministic corroboration required")

    if args.debug and analyst.last_debug:
        print()
        print("-" * 72)
        print("DEBUG — RAW OLLAMA CONTENT")
        print("-" * 72)
        print(analyst.last_debug.raw_content or "<empty>")
        print()
        print("DEBUG — DROPPED ITEMS")
        print(json.dumps(analyst.last_debug.dropped_items, indent=2, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
