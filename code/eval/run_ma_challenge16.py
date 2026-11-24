#!/usr/bin/env python3
"""Read-only 16-company M&A discovery challenge, with observable failure stages.

Run --mode local first, then --mode live against SEC with an identifying
user agent. This is a *pipeline diagnostic*, not an independently verified
M&A recall benchmark. No company-specific fixes are applied.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess
import sys

CODE = Path(__file__).resolve().parents[1]
ROOT = CODE.parent
sys.path.insert(0, str(CODE))

from root_entity_resolver import resolve_company_root
from providers.edgar_resolver import resolve_cik_by_name
from iterative_expansion import HelixFact, run_expansion
from providers.edgar_ma_provider import EdgarMAExpansionProvider
from providers.gleif_identity_fallback_provider import GleifIdentityFallbackProvider

DEFAULT_STUDY = ROOT / "data/eval_study/ma_challenge16_v1.json"


def cohort(path):
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    names = data.get("companies", [])
    if len(names) != 16 or len({x["id"] for x in names}) != 16:
        raise ValueError("Challenge cohort must have exactly 16 unique company IDs")
    if any(not x.get("query", "").strip() for x in names):
        raise ValueError("Blank company query in challenge")
    return data


def head_commit():
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True, stderr=subprocess.DEVNULL
        ).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def identity_probe(name, lei_db, rr_db, alias_db):
    try:
        result = resolve_company_root(
            name, lei_db=lei_db, rr_db=rr_db, alias_db=alias_db
        )
        return {
            "state": "COMPLETED",
            "status": result.status,
            "reason": result.reason,
            "endorsed_root": result.root.to_dict() if result.root else None,
            "seed_matches": [
                {"lei": row.get("lei"), "legal_name": row.get("legal_name"),
                 "matched_name": row.get("matched_name"),
                 "match_source": row.get("match_source", "GLEIF_CANONICAL")}
                for row in result.seed_matches
            ],
            "exploratory_candidates": [c.to_dict() for c in result.candidates[:10]],
            "candidate_count_reported": len(result.candidates),
        }
    except Exception as exc:
        return {"state": "ERROR", "error": f"{type(exc).__name__}: {exc}"}


def sec_probe(name, user_agent, tickers_fn=None, tickers=None):
    """A company_tickers-only probe. Non-match does NOT prove no SEC filings."""
    from providers import edgar_resolver
    try:
        if tickers is None:
            tickers = (tickers_fn or edgar_resolver._get_json)(
                edgar_resolver.SEC_TICKERS_URL, user_agent
            )
        cik = resolve_cik_by_name(name, user_agent, tickers=tickers)
        return {
            "state": "MATCHED" if cik else "NO_EXACT_TICKER_NAME_MATCH",
            "cik": cik,
            "note": (
                "This source is a public company ticker directory, not all SEC registrants."
                " No name match is not proof of no filing or no acquisition."
            ),
        }
    except Exception as exc:
        return {"state": "ERROR", "cik": None,
                "error": f"{type(exc).__name__}: {exc}"}


def expansion_probe(name, cik, user_agent, lei_db, rr_db, start, end, max_iterations,
                    fetch_fn=None, provider_factory=EdgarMAExpansionProvider):
    """Existing production SEC retrieval/parser and iteration engine; no acceptance override."""
    from providers.edgar_resolver import fetch_ma_filings
    load = fetch_fn or fetch_ma_filings
    try:
        # A missing ticker resolution does not eliminate the GLEIF test;
        # SEC filing retrieval remains not attempted without a verified CIK.
        if cik:
            data = load(cik, user_agent, start=start, end=end)
            filings = data.get("filings") or []
            sections = sum(len(f.get("sections") or []) for f in filings)
            # Never feed the seed company's SEC filings to a DIFFERENT
            # later pivot: that would fabricate counterparty/source linkage.
            # Only an independently resolved CIK may authorize that pivot's
            # own EDGAR retrieval in a future iteration.
            edgar = provider_factory(
                fetch_filings_fn=lambda pivot: (
                    data if pivot.value.casefold().strip() == name.casefold().strip()
                    else None
                )
            )
        else:
            filings = []
            sections = 0
            edgar = provider_factory(fetch_filings_fn=lambda pivot: None)

        seed = HelixFact(
            fact_type="COMPANY", value=name, identifier=None, source="SEED",
            confidence="HIGH", status="ACCEPTED", pivot_eligible=True
        )
        expansion = run_expansion(
            [seed],
            [edgar, GleifIdentityFallbackProvider(lei_db, rr_db)],
            max_iterations=max_iterations,
        )
        ma_facts = [f for f in expansion.facts if f.source == "EDGAR_MA"]
        events = []
        for fact in ma_facts:
            for evidence in fact.evidence:
                if evidence.get("type") == "EDGAR_MA_EVENT":
                    events.append({
                        "counterparty": fact.value,
                        "status": fact.status,
                        "trust_decision": evidence.get("trust_decision"),
                        "form": evidence.get("form"),
                        "filing_date": evidence.get("filing_date"),
                        "accession": evidence.get("accession"),
                        "document_url": evidence.get("document_url"),
                        "event_type": evidence.get("event_type"),
                        "event_status": evidence.get("status"),
                        "subject": evidence.get("subject"),
                        "object": evidence.get("object"),
                    })
        errors = [e for iteration in expansion.iterations for e in iteration.provider_errors]
        return {
            "state": "COMPLETED_WITH_PROVIDER_ERRORS" if errors else "COMPLETED",
            "filings_with_selected_sections": len(filings) if cik else None,
            "selected_sections": sections if cik else None,
            "sec_retrieval": "ATTEMPTED" if cik else "NOT_ATTEMPTED_NO_CIK",
            "expansion_iterations": expansion.iterations_run,
            "stop_reason": expansion.stop_reason,
            "all_facts": len(expansion.facts),
            "review_candidate_entities": [f.value for f in ma_facts],
            "ma_evidence_events": events,
            "provider_errors": errors,
            "limitations": [
                "Only filings selected by the production document/section retrieval path are counted.",
                "No candidate event does not establish absent M&A: document, section, entity or grammar may be missed.",
                "GLEIF consolidation facts are not M&A transaction evidence.",
                "Review-only events do not authorize recursion, and a non-pivotable finding is still a discovery.",
            ],
        }
    except Exception as exc:
        return {
            "state": "ERROR",
            "error": f"{type(exc).__name__}: {exc}",
            "sec_retrieval": "ATTEMPTED" if cik else "NOT_ATTEMPTED_NO_CIK",
        }


def summarize(rows):
    outcomes = Counter()
    for row in rows:
        identity = row["gleif_identity"]
        outcomes["gleif_query_errors"] += identity["state"] == "ERROR"
        outcomes["gleif_no_match"] += identity.get("status") == "NO_MATCH"
        outcomes["gleif_needs_review"] += identity.get("status") == "REVIEW_REQUIRED"
        outcomes["gleif_auto"] += identity.get("status") == "AUTO_RESOLVED"
        sec = row.get("sec_directory")
        if sec:
            outcomes["sec_ticker_name_matches"] += sec["state"] == "MATCHED"
            outcomes["sec_ticker_name_misses"] += sec["state"] == "NO_EXACT_TICKER_NAME_MATCH"
            outcomes["sec_ticker_errors"] += sec["state"] == "ERROR"
        expansion = row.get("ma_pipeline")
        if expansion:
            outcomes["pipeline_errors"] += expansion["state"] in ("ERROR", "COMPLETED_WITH_PROVIDER_ERRORS")
            outcomes["pipeline_review_candidates"] += len(expansion.get("review_candidate_entities") or [])
            outcomes["pipeline_evidence_events"] += len(expansion.get("ma_evidence_events") or [])
    return dict(sorted(outcomes.items()))


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--study", default=str(DEFAULT_STUDY))
    p.add_argument("--lei-db", default="data/processed/gleif_lei.sqlite")
    p.add_argument("--rr-db", default="data/processed/gleif_rr.sqlite")
    p.add_argument("--alias-db", default="data/processed/gleif_alias_compact_full.sqlite")
    p.add_argument("--mode", choices=("local", "live"), default="local")
    p.add_argument("--user-agent", help="Required in live mode: actual name and email for SEC")
    p.add_argument("--only", action="append", help="Run only named cohort ID; repeat for several")
    p.add_argument("--start", default="2015-01-01")
    p.add_argument("--end", default="2026-11-24")
    p.add_argument("--max-iterations", type=int, default=2)
    p.add_argument("--out", required=True, help="New JSON report; existing file refused")
    a = p.parse_args(argv)
    if a.mode == "live" and (not a.user_agent or "@" not in a.user_agent or "example.com" in a.user_agent):
        p.error("--mode live requires a real SEC --user-agent 'Name email@domain'")
    if a.max_iterations < 1:
        p.error("--max-iterations must be >= 1")
    study = cohort(a.study)
    companies = study["companies"]
    if a.only:
        missing = set(a.only) - {x["id"] for x in companies}
        if missing:
            p.error(f"Unknown cohort ID(s): {', '.join(sorted(missing))}")
        companies = [x for x in companies if x["id"] in set(a.only)]
    # Intentional: no silent query spelling corrections or alias substitution.
    rows = []
    # Resolve the SEC ticker directory once per run. A failure here remains
    # an observable source error rather than being retried 16 times.
    tickers = None
    ticker_error = None
    if a.mode == "live":
        from providers.edgar_resolver import _get_json, SEC_TICKERS_URL
        try:
            tickers = _get_json(SEC_TICKERS_URL, a.user_agent)
        except Exception as exc:
            ticker_error = f"{type(exc).__name__}: {exc}"
    for index, spec in enumerate(companies, 1):
        print(f"[{index}/{len(companies)}] {spec['id']}: {spec['query']}", file=sys.stderr, flush=True)
        record = {
            "id": spec["id"], "query_as_supplied": spec["query"],
            "notes": spec.get("notes"),
            "gleif_identity": identity_probe(spec["query"], a.lei_db, a.rr_db, a.alias_db),
        }
        if a.mode == "live":
            sec = (
                sec_probe(spec["query"], a.user_agent, tickers=tickers)
                if ticker_error is None else
                {"state": "ERROR", "cik": None, "error": ticker_error}
            )
            record["sec_directory"] = sec
            if sec["state"] == "ERROR":
                record["ma_pipeline"] = {
                    "state": "NOT_ATTEMPTED_SEC_DIRECTORY_ERROR",
                    "sec_retrieval": "NOT_ATTEMPTED",
                }
            else:
                record["ma_pipeline"] = expansion_probe(
                    spec["query"], sec.get("cik"), a.user_agent,
                    a.lei_db, a.rr_db, a.start, a.end, a.max_iterations
                )
        rows.append(record)
    report = {
        "study_id": study["study_id"], "mode": a.mode,
        "run_timestamp": datetime.now(timezone.utc).isoformat(),
        "git_commit": head_commit(),
        "frozen_cohort_size": len(study["companies"]),
        "queries_executed": len(rows),
        "start": a.start if a.mode == "live" else None,
        "end": a.end if a.mode == "live" else None,
        "source_limits": [
            "GLEIF is a current/snapshot legal-identity and consolidation source, not comprehensive M&A history.",
            "SEC company_tickers.json is not a complete registrant directory; private and foreign companies may have no ticker.",
            "SEC production retrieval can miss documents, exhibits, and older filings; a zero is not a negative gold label.",
            "User spelling preserved verbatim; mismatched names are flagged for later identity lookup, not auto-corrected.",
            "This run has no independent ground-truth transaction labels and cannot report M&A recall.",
        ],
        "summary": summarize(rows), "companies": rows,
        "quality": "NOT_SCORED",
    }
    output = Path(a.out)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print(json.dumps({"study_id": report["study_id"], "mode": a.mode,
                      "queries_executed": len(rows), "summary": report["summary"],
                      "quality": "NOT_SCORED", "out": str(output.resolve())}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
