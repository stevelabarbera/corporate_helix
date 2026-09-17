#!/usr/bin/env python3
"""Capture an M&A-S1 stage-by-stage baseline without tuning production behavior.

The runner intentionally keeps its audit corpus separate from the production
resolver/provider.  Production output answers what Helix emitted; the audit
corpus lets us distinguish retrieval, locator, entity, event, and candidate
failures for independently-declared gold events.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable

ROOT = Path(__file__).resolve().parents[2]
CODE = ROOT / "code"
if str(CODE) not in sys.path:
    sys.path.insert(0, str(CODE))

from iterative_expansion import HelixFact
from parsers.edgar_longform_locator import locate_ma_regions
from providers.edgar_ma_provider import EdgarMAExpansionProvider, other_party
from providers.edgar_resolver import (
    _document_url,
    _get_text,
    _load_submissions,
    _rv,
    identity_key,
    item_sections,
    resolve_cik_by_name,
    strip_html,
)

STAGES = (
    "cik_resolved",
    "filings_retrieved",
    "relevant_text_present",
    "locator_captured",
    "entity_recognized",
    "event_extracted",
    "candidate_emitted",
)
AUDIT_FORMS = {"8-K", "8-K/A", "10-K", "10-K/A"}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text())


def git_head() -> str:
    return subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()


def company_spec(study: dict[str, Any], company_id: str) -> dict[str, Any]:
    for spec in study["companies"]:
        if spec["id"] == company_id:
            return spec
    raise ValueError(f"Unknown study company id: {company_id}")


def name_variants(event: dict[str, Any]) -> list[str]:
    values = [event.get("counterparty"), *(event.get("aliases") or [])]
    return [str(v).strip() for v in values if str(v or "").strip()]


def name_in_text(names: Iterable[str], text: str) -> bool:
    folded = text.casefold()
    return any(name.casefold() in folded for name in names)


def same_company(candidate: str | None, names: Iterable[str]) -> bool:
    key = identity_key(candidate or "")
    return bool(key) and any(key == identity_key(name) for name in names)


def event_matches_gold(event: dict[str, Any], gold: dict[str, Any], names: Iterable[str]) -> bool:
    """Match the independently declared event, not merely its counterparty."""
    if not any(same_company(event.get(role), names) for role in ("subject", "object")):
        return False
    expected_type = str(gold.get("event_type") or "").strip().upper()
    expected_status = str(gold.get("status") or "").strip().upper()
    actual_type = str(event.get("event_type") or "").strip().upper()
    actual_status = str(event.get("status") or "").strip().upper()
    if expected_type and actual_type != expected_type:
        return False
    if expected_status and actual_status != expected_status:
        return False
    return True


def collect_audit_filings(
    cik: str,
    user_agent: str,
    *,
    start: str,
    end: str,
    load_submissions_fn: Callable = _load_submissions,
    get_text_fn: Callable = _get_text,
) -> tuple[str, list[dict[str, Any]], list[dict[str, str]]]:
    """Download the frozen study corpus while preserving unselected raw text."""
    cik10, submissions = load_submissions_fn(cik, user_agent)
    recent = submissions["filings"]["recent"]
    filings: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for i, form in enumerate(recent.get("form", [])):
        if form not in AUDIT_FORMS:
            continue
        filing_date = _rv(recent, "filingDate", i, "")
        if not (start <= filing_date <= end):
            continue
        accession = _rv(recent, "accessionNumber", i)
        primary_doc = _rv(recent, "primaryDocument", i)
        if not accession or not primary_doc:
            continue
        url = _document_url(cik10, accession, primary_doc)
        try:
            raw_text = strip_html(get_text_fn(url, user_agent))
        except Exception as exc:  # preserve partial baseline instead of erasing it
            errors.append({"accession": accession, "error": f"{type(exc).__name__}: {exc}"})
            continue

        if form in {"8-K", "8-K/A"}:
            items = _rv(recent, "items", i, "") or ""
            selected = []
            if "1.01" in items or "2.01" in items:
                selected = [s for s in item_sections(raw_text) if s["item"] in {"1.01", "2.01"}]
        else:
            items = ""
            selected = locate_ma_regions(raw_text, form=form)
        filings.append({
            "accession": accession,
            "filing_date": filing_date,
            "form": form,
            "items": items,
            "primary_document": primary_doc,
            "document_url": url,
            "raw_text": raw_text,
            "sections": selected,
        })
    return cik10, filings, errors


def analyze_event(
    gold: dict[str, Any],
    filings: list[dict[str, Any]],
    parsed_sections: list[dict[str, Any]],
    candidates: list[HelixFact],
) -> dict[str, Any]:
    names = name_variants(gold)
    raw_hits = [f for f in filings if name_in_text(names, f["raw_text"])]
    selected_hits = [
        {
            "accession": row["filing"].get("accession"),
            "form": row["filing"].get("form"),
            "section": row["section"].get("item"),
            "locator_terms": row["section"].get("locator_terms") or [],
        }
        for row in parsed_sections
        if name_in_text(names, row["section"]["text"])
    ]
    entity_hits = []
    event_hits = []
    for row in parsed_sections:
        parsed = row["parsed"]
        if any(same_company(org, names) for org in parsed["fused"].get("orgs", [])):
            entity_hits.append(row["filing"].get("accession"))
        for event in parsed.get("completed_events", []):
            # Event extraction is deliberately measured before provider
            # linkage.  Requiring other_party() here would collapse a pivot
            # name/alias mismatch into EVENT_GRAMMAR_MISS even when the
            # extractor produced a perfectly usable event involving the gold
            # counterparty.  Candidate emission below remains the end-to-end
            # provider/linkage measurement.
            matched_roles = [
                role for role in ("subject", "object")
                if same_company(event.get(role), names)
            ]
            if matched_roles and event_matches_gold(event, gold, names):
                event_hits.append({
                    "accession": row["filing"].get("accession"),
                    "event_type": event.get("event_type"),
                    "status": event.get("status"),
                    "extraction_rule": event.get("extraction_rule"),
                    "counterparty_roles": matched_roles,
                    "provider_other_party": other_party(event, row["pivot_name"]),
                })
    candidate_hits = [f for f in candidates if same_company(f.value, names)]

    stages = {
        "filings_retrieved": bool(filings),
        "relevant_text_present": bool(raw_hits),
        "locator_captured": bool(selected_hits),
        "entity_recognized": bool(entity_hits),
        "event_extracted": bool(event_hits),
        "candidate_emitted": bool(candidate_hits),
    }
    deepest = "CIK_RESOLVED"
    for stage in STAGES[1:]:
        if stages[stage]:
            deepest = stage.upper()
        else:
            break
    return {
        **gold,
        "stages": stages,
        "deepest_stage": deepest,
        "evidence": {
            "raw_text_accessions": sorted({f["accession"] for f in raw_hits}),
            "selected_section_hits": selected_hits,
            "entity_accessions": sorted({x for x in entity_hits if x}),
            "event_hits": event_hits,
            "candidate_names": sorted({f.value for f in candidate_hits}),
        },
    }


def aggregate_pipeline(cik: str | None, events: list[dict[str, Any]]) -> dict[str, bool | None]:
    out: dict[str, bool | None] = {"cik_resolved": bool(cik)}
    for stage in STAGES[1:]:
        vals = [event["stages"][stage] for event in events]
        out[stage] = any(vals) if vals else None
    return out


def failure_classes(events: list[dict[str, Any]]) -> list[str]:
    labels = set()
    for event in events:
        s = event["stages"]
        if not s["relevant_text_present"]:
            labels.add("DISCLOSURE_NOT_IN_RETRIEVED_CORPUS")
        elif not s["locator_captured"]:
            labels.add("LOCATOR_MISS")
        elif not s["entity_recognized"]:
            labels.add("ENTITY_RECOGNITION_MISS")
        elif not s["event_extracted"]:
            labels.add("EVENT_GRAMMAR_MISS")
        elif not s["candidate_emitted"]:
            labels.add("CANDIDATE_EMISSION_MISS")
    return sorted(labels)


def observed_primitives(events: list[dict[str, Any]]) -> list[str]:
    labels = set()
    for event in events:
        for hit in event["evidence"]["selected_section_hits"]:
            if hit.get("form"):
                labels.add(f'FORM:{str(hit["form"]).upper()}')
            if hit.get("section"):
                labels.add(f'SECTION:{str(hit["section"]).upper()}')
            for term in hit.get("locator_terms") or []:
                labels.add(f'LOCATOR_SIGNAL:{str(term).upper()}')
        for hit in event["evidence"]["event_hits"]:
            if hit.get("extraction_rule"):
                labels.add(f'EXTRACTION_RULE:{str(hit["extraction_rule"]).upper()}')
    return sorted(labels)


def run_baseline(
    spec: dict[str, Any],
    gold: dict[str, Any],
    *,
    user_agent: str,
    start: str,
    end: str,
    collector: Callable = collect_audit_filings,
    provider_factory: Callable[..., EdgarMAExpansionProvider] = EdgarMAExpansionProvider,
    resolve_fn: Callable[..., str | None] = resolve_cik_by_name,
) -> dict[str, Any]:
    cik = spec.get("cik") or resolve_fn(spec["company"], user_agent)
    if not cik:
        unresolved_events = []
        for event in gold.get("events", []):
            unresolved_events.append({
                **event,
                "stages": {stage: None for stage in STAGES[1:]},
                "deepest_stage": "CIK_UNRESOLVED",
                "evidence": {
                    "raw_text_accessions": [],
                    "selected_section_hits": [],
                    "entity_accessions": [],
                    "event_hits": [],
                    "candidate_names": [],
                },
            })
        return {
            "company_id": spec["id"], "company": spec["company"],
            "baseline_commit": git_head(), "run_timestamp": datetime.now(timezone.utc).isoformat(),
            "pipeline": {stage: (False if stage == "cik_resolved" else None) for stage in STAGES},
            "gold_events": unresolved_events, "unmatched_candidates": [],
            "retrieval": {"filing_count": 0, "errors": []}, "observed_primitives": [],
            "failure_classes": ["CIK_RESOLUTION_MISS"], "notes": "CIK resolution failed; no SEC requests made.",
        }

    cik10, filings, fetch_errors = collector(cik, user_agent, start=start, end=end)
    pivot = HelixFact(
        fact_type="COMPANY", value=spec["company"], identifier=cik10,
        source="SEED", confidence="HIGH", status="ACCEPTED", pivot_eligible=True,
    )
    frozen_data = {"company": spec["company"], "cik": cik10, "filings": [
        {k: v for k, v in f.items() if k != "raw_text"} for f in filings
    ]}
    provider = provider_factory(fetch_filings_fn=lambda _: frozen_data)
    candidates = list(provider(pivot, 1))
    parsed_sections = []
    for filing in frozen_data["filings"]:
        for section in filing.get("sections", []):
            parsed_sections.append({
                "filing": filing, "section": section, "pivot_name": pivot.value,
                "parsed": provider._parse_filing_section(section["text"], section.get("item")),
            })

    events = [analyze_event(event, filings, parsed_sections, candidates) for event in gold.get("events", [])]
    emitted_keys = {identity_key(f.value) for f in candidates}
    matched_keys = {identity_key(n) for event in gold.get("events", []) for n in name_variants(event)}
    unmatched = [
        {"name": f.value, "status": f.status, "confidence": f.confidence,
         "evidence_count": len(f.evidence)}
        for f in candidates if identity_key(f.value) in emitted_keys - matched_keys
    ]
    return {
        "company_id": spec["id"], "company": spec["company"],
        "baseline_commit": git_head(), "run_timestamp": datetime.now(timezone.utc).isoformat(),
        "scope": {"start": start, "end": end, "forms": sorted(AUDIT_FORMS)},
        "cik": cik10, "pipeline": aggregate_pipeline(cik10, events),
        "gold_events": events, "unmatched_candidates": unmatched,
        "retrieval": {"filing_count": len(filings), "errors": fetch_errors},
        "observed_primitives": observed_primitives(events),
        "failure_classes": failure_classes(events),
        "notes": "Measurement-only M&A-S1 run; production resolver, locator, extractor, trust, and recursion behavior unchanged.",
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--company", required=True, help="Study company id, e.g. tenable")
    ap.add_argument("--study", type=Path, default=ROOT / "data/eval_study/ma_saturation_pilot_v1.json")
    ap.add_argument("--gold-dir", type=Path, default=ROOT / "data/eval_gold")
    ap.add_argument("--results", type=Path, default=ROOT / "data/eval_study/ma_saturation_results")
    ap.add_argument("--start", default="2015-01-01")
    ap.add_argument("--end", default="2026-12-31")
    ap.add_argument("--user-agent", default="CorporationHelix research contact@example.com")
    ap.add_argument("--stdout", action="store_true", help="Print JSON instead of writing the study result")
    args = ap.parse_args()

    study = load_json(args.study)
    spec = company_spec(study, args.company)
    gold_path = args.gold_dir / f"{args.company}.json"
    if not gold_path.exists():
        raise SystemExit(f"Gold file not found: {gold_path}")
    result = run_baseline(
        spec, load_json(gold_path), user_agent=args.user_agent,
        start=args.start, end=args.end,
    )
    rendered = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    if args.stdout:
        print(rendered, end="")
    else:
        args.results.mkdir(parents=True, exist_ok=True)
        output = args.results / f"{args.company}.json"
        output.write_text(rendered)
        print(f"Wrote {output.relative_to(ROOT)}")
        print(f"CIK: {result.get('cik') or 'UNRESOLVED'} | filings: {result.get('retrieval', {}).get('filing_count', 0)}")
        for event in result.get("gold_events", []):
            print(f"  {event.get('counterparty', event.get('id'))}: {event.get('deepest_stage', 'CIK_RESOLVED')}")
        print(f"Unmatched candidates: {len(result.get('unmatched_candidates', []))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
