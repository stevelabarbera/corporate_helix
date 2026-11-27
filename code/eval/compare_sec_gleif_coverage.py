#!/usr/bin/env python3
"""Read-only SEC/GLEIF coverage comparison: no SEC fetch, no graph mutations.

This reports what the *existing* L1/L2 resolver can say about the seed and
each historical SEC sentinel counterparty. It does NOT call a GLEIF parent
relationship a merger, and does not modify frozen SEC stage results.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[2]
CODE = ROOT / "code"
if str(CODE) not in sys.path:
    sys.path.insert(0, str(CODE))

from root_entity_resolver import normalize_name, resolve_company_root


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def identity_view(result: Any, query: str, as_of: str) -> dict[str, Any]:
    """Keep the original query distinct from a proposed ultimate root."""
    seeds = getattr(result, "seed_matches", []) or []
    exact = [s for s in seeds
             if not s.get("match_source")
             and normalize_name(s.get("legal_name") or "") == normalize_name(query)]
    # Root recommendation != seed identity; present both separately.
    root = getattr(result, "root", None)
    candidates = getattr(result, "candidates", []) or []
    return {
        "query": query,
        "as_of_date": as_of,
        "status": getattr(result, "status"),
        "confidence": getattr(result, "confidence"),
        "reason": getattr(result, "reason"),
        "exact_seed_leis": sorted({s["lei"] for s in exact if s.get("lei")}),
        "seed_count": len(seeds),
        "seed_candidates": [{
            "lei": s.get("lei"), "legal_name": s.get("legal_name"),
            "entity_status": s.get("entity_status"),
            "match_source": s.get("match_source", "LEGAL_NAME"),
        } for s in seeds[:10]],
        "endorsed_root": ({"lei": root.lei, "legal_name": root.legal_name,
                           "entity_status": root.entity_status} if root else None),
        "proposed_roots": [{
            "lei": c.lei, "legal_name": c.legal_name,
            "direct_parent_votes": c.direct_parent_votes,
            "ultimate_parent_votes": c.ultimate_parent_votes,
            "coverage": c.coverage,
        } for c in candidates[:5]],
        "historical_caveat": (
            "A current GLEIF snapshot filtered with as_of_date does not "
            "reconstruct historical registration or relationship status."
        ),
    }


def attempt_resolution(name: str, as_of: str, resolver: Callable[..., Any],
                       lei_index: str, rr_index: str) -> dict[str, Any]:
    try:
        result = resolver(name, lei_index, rr_index, as_of_date=as_of)
        view = identity_view(result, name, as_of)
        view["check"] = "CHECKED"
        return view
    except (OSError, ValueError, RuntimeError) as exc:
        # Never conflate database access failure with a genuine GLEIF no-match.
        return {
            "query": name, "as_of_date": as_of, "check": "ERROR",
            "status": "ERROR", "error": f"{type(exc).__name__}: {exc}",
            "exact_seed_leis": [], "endorsed_root": None,
        }


def compare(study: dict[str, Any], results_dir: Path, gold_dir: Path,
            lei_index: str, rr_index: str, *, as_of: str,
            resolver: Callable[..., Any] = resolve_company_root) -> dict[str, Any]:
    date.fromisoformat(as_of)  # reject invalid calendar dates early
    cache: dict[tuple[str, str], dict[str, Any]] = {}

    def get(name: str, at: str) -> dict[str, Any]:
        key = (name, at)
        if key not in cache:
            cache[key] = attempt_resolution(name, at, resolver, lei_index, rr_index)
        return cache[key]

    companies = []
    for spec in study["companies"]:
        company_id = spec["id"]
        sec_path = results_dir / f"{company_id}.json"
        gold_path = gold_dir / f"{company_id}.json"
        sec = read_json(sec_path) if sec_path.is_file() else None
        gold = read_json(gold_path) if gold_path.is_file() else None
        seed_now = get(spec["company"], as_of)
        sentinel_rows = []
        # Do not pretend the SEC stage ran when an output file is missing.
        if gold:
            sec_events = {e.get("id"): e for e in (sec or {}).get("gold_events", [])}
            for g in gold.get("events", []):
                event_date = g.get("approx_date") or as_of
                date.fromisoformat(event_date)
                counterparty = g["counterparty"]
                sec_event = sec_events.get(g.get("id"))
                flags = (sec_event or {}).get("stages") or {}
                extracted = flags.get("event_extracted") is True
                emitted = flags.get("candidate_emitted") is True
                sentinel_rows.append({
                    "gold_id": g.get("id"),
                    "counterparty": counterparty,
                    "expected_event_type": g.get("event_type"),
                    "expected_status": g.get("status"),
                    "event_date": event_date,
                    "sec": {
                        "check": "CHECKED" if sec_event else "NOT_CHECKED",
                        "event_extracted": (extracted if sec_event else None),
                        "counterparty_candidate_emitted": (emitted if sec_event else None),
                        "matching_event_and_candidate": (extracted and emitted if sec_event else None),
                        "evidence_accessions": sorted({
                            hit.get("accession") for hit in
                            ((sec_event or {}).get("evidence") or {}).get("event_hits", [])
                            if hit.get("accession")
                        }),
                    },
                    "gleif_counterparty_current": get(counterparty, as_of),
                    "gleif_seed_at_event_date": get(spec["company"], event_date),
                    "gleif_counterparty_at_event_date": get(counterparty, event_date),
                    "reconciliation": (
                        "REVIEW_SOURCES_SEPARATELY"
                        if sec_event else "SEC_NOT_CHECKED"
                    ),
                    "acquisition_inferred_from_gleif": False,
                })
        companies.append({
            "id": company_id, "company": spec["company"],
            "identifiers": {"sec_cik": spec.get("cik"), "gleif_lei": None},
            "sec": {
                "check": "CHECKED" if sec else "NOT_CHECKED",
                "retrieval_errors": (sec.get("retrieval") or {}).get("errors") if sec else None,
            },
            "gleif_seed_current": seed_now,
            "sentinel_events": sentinel_rows,
        })
    return {
        "study_id": study.get("study_id"),
        "comparison_as_of_date": as_of,
        "quality": "READ_ONLY_COVERAGE_DIAGNOSTIC_NOT_MA_RECALL",
        "policy": {
            "infer_ma_from_gleif": False,
            "auto_authorize_asm_scope": False,
            "gleif_historical_snapshot_complete": False,
            "provider_results_reconciled_into_graph": False,
        },
        "companies": companies,
    }


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--study", default="data/eval_study/ma_recall_four_v1.json")
    p.add_argument("--results", default="data/eval_study/ma_recall_four_results")
    p.add_argument("--gold-dir", default="data/eval_gold/ma_recall_four")
    p.add_argument("--lei-index", default="data/processed/gleif_lei.sqlite")
    p.add_argument("--rr-index", default="data/processed/gleif_rr.sqlite")
    p.add_argument("--as-of", default=date.today().isoformat())
    p.add_argument("--out", required=True)
    a = p.parse_args(argv)
    report = compare(read_json(Path(a.study)), Path(a.results),
                     Path(a.gold_dir), a.lei_index, a.rr_index, as_of=a.as_of)
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("x", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
        f.write("\n")
    for c in report["companies"]:
        print(f'{c["id"]}: SEC={c["sec"]["check"]} '
              f'GLEIF seed={c["gleif_seed_current"]["status"]}')
        for e in c["sentinel_events"]:
            print(f'  {e["counterparty"]}: '
                  f'SEC event={e["sec"]["event_extracted"]} '
                  f'GLEIF current={e["gleif_counterparty_current"]["status"]} '
                  f'GLEIF as-of-event={e["gleif_counterparty_at_event_date"]["status"]}')
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
