#!/usr/bin/env python3
"""
Corporation Helix -- run the coverage evaluation for one or more companies.

For each company, loads its data/eval_gold/<company>.json (written BLIND,
before any filing text was examined -- see each file's gold_sources and
scoping notes) and its data/eval_raw/<company>*.json (real fetched filing
text), runs the actual EdgarMAExpansionProvider parsing logic against that
text, and scores the result with coverage_harness.

Usage:
    python3 run_coverage_eval.py --gold lumen.json --raw lumen_level3_real.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from coverage_harness import GoldEvent, SystemEvent, aggregate_reports, score_company
from providers.edgar_ma_provider import EdgarMAExpansionProvider
from iterative_expansion import HelixFact

GOLD_DIR = Path(__file__).resolve().parents[2] / "data" / "eval_gold"
RAW_DIR = Path(__file__).resolve().parents[2] / "data" / "eval_raw"


def system_events_for_company(company: str, raw_paths: list[Path], aliases: list[str] | None = None) -> list[SystemEvent]:
    """
    Run discovery for every known name the company has gone by, not just
    its current one. A real filing from before a rebrand/restructuring
    (Lumen was CenturyLink until 2020; Disney's holdco swapped names with
    its own former self at closing) never mentions the CURRENT name at
    all -- querying only that name silently produces zero events, which
    looks identical to "the parser found nothing" even when it actually
    would have, under the name the filing itself uses. This tries every
    alias from the gold file's aliases_ok list as its own pivot and merges
    results, deduping by (counterparty, event_type, status).
    """
    combined_filings = []
    for path in raw_paths:
        data = json.loads(path.read_text())
        combined_filings.extend(data.get("filings", []))
    fixture = {"company": company, "cik": "", "filings": combined_filings}
    provider = EdgarMAExpansionProvider(fetch_filings_fn=lambda p: fixture)

    seen: set[tuple[str, str, str]] = set()
    events: list[SystemEvent] = []
    for name in [company, *(aliases or [])]:
        pivot = HelixFact(
            fact_type="COMPANY", value=name, identifier=None,
            source="SEED", confidence="HIGH", status="ACCEPTED", pivot_eligible=True,
        )
        facts = list(provider(pivot, 1))
        for fact in facts:
            for ev in fact.evidence:
                key = (fact.value, ev.get("event_type", ""), ev.get("status", ""))
                if key in seen:
                    continue
                seen.add(key)
                events.append(SystemEvent(
                    counterparty=fact.value,
                    event_type=ev.get("event_type", ""),
                    status=ev.get("status", ""),
                    accession=ev.get("accession", ""),
                ))
    return events


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--gold", nargs="+", required=True, help="Gold JSON filename(s) under data/eval_gold/")
    args = ap.parse_args()

    reports = []
    for gold_name in args.gold:
        gold_data = json.loads((GOLD_DIR / gold_name).read_text())
        company = gold_data["company"]
        gold_events = [GoldEvent.from_mapping(e) for e in gold_data["events"]]

        stem = Path(gold_name).stem
        raw_paths = sorted(RAW_DIR.glob(f"{stem}*.json"))

        if not raw_paths:
            print(f"[{company}] no raw filing data found in data/eval_raw/{stem}*.json -- skipping")
            continue

        system_events = system_events_for_company(company, raw_paths, gold_data.get("aliases_ok"))
        report = score_company(company, gold_events, system_events)
        reports.append(report)

        print(f"=== {company} ===")
        print(f"  Raw filing sources used: {[p.name for p in raw_paths]}")
        for m in report.matches:
            print(f"  [{m.stage.value:20s}] {m.counterparty:45s} "
                  f"gold={m.gold_event_type}/{m.gold_status}  system={m.system_event_type}/{m.system_status}")
        print(f"  Recall: {report.recall_hits}/{report.total_gold}")
        print()

    if reports:
        print("=== AGGREGATE ===")
        print(json.dumps(aggregate_reports(reports), indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
