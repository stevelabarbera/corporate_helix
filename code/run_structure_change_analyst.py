#!/usr/bin/env python3
"""Run the guarded structure-change analyst against one evidence packet."""

from __future__ import annotations

import argparse
import json
import sys
from copy import deepcopy
from pathlib import Path


CODE_DIR = Path(__file__).resolve().parent
if str(CODE_DIR) not in sys.path:
    sys.path.insert(0, str(CODE_DIR))

from adjudication.structure_change_packet import ALLOWED_DECISIONS
from analysts.structure_change_analyst import OllamaStructureChangeAnalyst


LLM_REVIEW_STATUS = "LLM_REVIEWED_PENDING_HUMAN"


def review_packet(packet, analyst):
    """Return a reviewed copy while preserving the human/final trust boundary."""
    contract = packet.get("model_contract") or {}
    packet_decisions = contract.get("allowed_decisions")
    if packet_decisions != ALLOWED_DECISIONS:
        raise ValueError(
            "Packet model contract is stale; regenerate the evidence packet before review"
        )

    reviewed = deepcopy(packet)
    adjudication = reviewed.get("adjudication")
    if not isinstance(adjudication, dict):
        raise ValueError("Packet is missing its adjudication record")
    if adjudication.get("final") is not None:
        raise ValueError("Refusing to overwrite a packet with a final adjudication")

    result = analyst.analyze(reviewed)
    if not result.get("advisory_only") or result.get("creates_trusted_graph_edges") is not False:
        raise ValueError("Analyst result violated the advisory-only trust boundary")

    adjudication["llm"] = result
    adjudication["status"] = LLM_REVIEW_STATUS
    return reviewed


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Run guarded, advisory-only LLM review of a structure-change evidence packet."
    )
    parser.add_argument("--packet", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--model", default="gemma3:1b")
    parser.add_argument("--endpoint", default="http://127.0.0.1:11434/api/chat")
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace an existing output file intentionally.",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = _parse_args(argv)
    if args.out.exists() and not args.overwrite:
        print(f"Output already exists: {args.out}", file=sys.stderr)
        print("Use --overwrite only for an intentional replacement.", file=sys.stderr)
        return 2

    try:
        packet = json.loads(args.packet.read_text())
        analyst = OllamaStructureChangeAnalyst(
            model=args.model,
            endpoint=args.endpoint,
            timeout=args.timeout,
        )
        reviewed = review_packet(packet, analyst)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"Structure-change review failed: {exc}", file=sys.stderr)
        return 1

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(reviewed, indent=2, ensure_ascii=False) + "\n")

    result = reviewed["adjudication"]["llm"]
    print(f"Wrote advisory review -> {args.out}")
    print(f"Decision: {result['decision']} | confidence: {result['confidence']}")
    print(f"Evidence: {', '.join(result['supporting_evidence_ids']) or 'none'}")
    print("Trust: advisory only; human/final adjudication remains unset")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
