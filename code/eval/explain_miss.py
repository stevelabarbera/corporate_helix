#!/usr/bin/env python3
"""
Explain WHY a gold event was (or was not) found -- the sentences, not the stage name.

The baseline harness says "ENTITY_RECOGNIZED" or "LOCATOR_CAPTURED"; this prints
the verbatim passages in the retrieved filings that mention the counterparty,
what each extractor backend saw in them, and a verdict:

  NOT_IN_REGION          name is in the filing but outside every located region
  ENTITY_NOT_SEEN        no backend produced the name as an organization
  ENTITY_SPLIT_VOTE      backends saw it under different spellings ("X, Inc." vs "X"); pooled
                         weight WOULD clear the threshold, but the fusion counts spellings separately
  ENTITY_BELOW_THRESHOLD some backend saw it, but total weight < ensemble threshold
  EVENT_GRAMMAR_MISS     organization recognized, but no event involves it
  EVENT_TYPE_MISMATCH    an event involves it, but not the gold type/status
  FOUND                  an event matching the gold type/status exists

It changes nothing; it parses with exactly the code the baseline harness uses.

  python3 code/eval/explain_miss.py --company crowdstrike --counterparty SGNL \\
      --study data/eval_study/ma_audit_v2.json --user-agent "$SEC_USER_AGENT"

  # offline, on a saved document, no gold file needed:
  python3 code/eval/explain_miss.py --text-file filing.htm --names "SGNL,Seraphic"

Downloads are cached under .helix_cache/ (git-ignored) so repeat runs are fast.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[2]
CODE = ROOT / "code"
if str(CODE) not in sys.path:
    sys.path.insert(0, str(CODE))

from eval.run_ma_s1_baseline import (  # noqa: E402
    identity_key,
    collect_audit_filings, company_spec, event_matches_gold, load_json, name_variants, same_company,
)
from parsers.edgar_longform_locator import locate_ma_regions  # noqa: E402
from providers.edgar_ma_provider import EdgarMAExpansionProvider  # noqa: E402
from providers.edgar_resolver import _get_text, strip_html  # noqa: E402

VERDICTS = ("NOT_IN_REGION", "ENTITY_NOT_SEEN", "ENTITY_SPLIT_VOTE", "ENTITY_BELOW_THRESHOLD",
            "EVENT_GRAMMAR_MISS", "EVENT_TYPE_MISMATCH", "FOUND")
_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z“\"(])")


# ----------------------------------------------------------------- passages

def find_passages(text: str, names: list[str], *, context: int = 1, limit: int = 6) -> list[str]:
    """Sentences mentioning any name, plus `context` sentences either side; overlaps merged."""
    sentences = [s.strip() for s in _SENT_SPLIT.split(text) if s.strip()]
    folded = [n.casefold() for n in names if n]
    hit_idx = [i for i, s in enumerate(sentences) if any(n in s.casefold() for n in folded)]
    spans: list[list[int]] = []
    for i in hit_idx:
        lo, hi = max(0, i - context), min(len(sentences), i + context + 1)
        if spans and lo <= spans[-1][1]:
            spans[-1][1] = max(spans[-1][1], hi)
        else:
            spans.append([lo, hi])
    return [" ".join(sentences[lo:hi]) for lo, hi in spans[:limit]]


# -------------------------------------------------------------- backend view

def backend_view(extractor, passage: str, names: list[str]) -> dict[str, Any]:
    """Per backend: which of its organizations look like the counterparty, and its weight."""
    folded = [n.casefold() for n in names if n]
    out = {}
    for backend in extractor.backends:
        orgs = backend.parse(passage).get("orgs", [])
        hits = [o for o in orgs if any(n in o.casefold() or o.casefold() in n for n in folded)]
        out[backend.name] = {"weight": extractor.weights.get(backend.name), "orgs_matching_name": hits}
    return out


def _loosely_same(candidate: str, names: list[str]) -> bool:
    """True when one identity key is a whole-token prefix of the other ("sgnl" vs "sgnl ai")."""
    ck = identity_key(candidate or "").split()
    for n in names:
        nk = identity_key(n).split()
        short, long_ = (ck, nk) if len(ck) <= len(nk) else (nk, ck)
        if short and long_[:len(short)] == short:
            return True
    return False


def verdict_for(*, in_region: bool, votes: dict[str, Any], threshold: float, fused_orgs: list[str],
                events: list[dict[str, Any]], gold: dict[str, Any] | None, names: list[str]) -> tuple[str, str]:
    if not in_region:
        return "NOT_IN_REGION", "the name appears in the filing but the locator did not select this passage"
    seen = {b: v for b, v in votes.items() if v["orgs_matching_name"]}
    recognized = [o for o in fused_orgs if same_company(o, names)]
    loose = [] if recognized else [o for o in fused_orgs if _loosely_same(o, names)]
    note = ""
    if loose:
        recognized = loose
        note = (f" [NAME FORM: the extractor recognised {loose}, which the baseline's identity match treats as a "
                f"different company from the gold name {names}; add the legal name to the gold aliases]")
    if not recognized:
        if not seen:
            return "ENTITY_NOT_SEEN", "no backend produced the name as an organization"
        total = sum((v["weight"] or 0) for v in seen.values())
        spellings = sorted({o for v in seen.values() for o in v["orgs_matching_name"]})
        if total >= threshold and len(spellings) > 1:
            return ("ENTITY_SPLIT_VOTE",
                    f"{sorted(seen)} saw it as {spellings}; pooled weight {total} >= threshold {threshold}, "
                    f"but each spelling is counted on its own")
        return ("ENTITY_BELOW_THRESHOLD",
                f"seen by {sorted(seen)} for total weight {total} < threshold {threshold}")
    involved = [e for e in events if any(same_company(e.get(r), names) for r in ("subject", "object"))]
    if not involved:
        return "EVENT_GRAMMAR_MISS", "organization recognized, but no event involves it" + note
    if gold and not any(event_matches_gold(e, gold, names) for e in involved):
        got = sorted({f"{e['event_type']}/{e['status']}" for e in involved})
        return ("EVENT_TYPE_MISMATCH",
                f"event(s) found {got} but gold expects {gold.get('event_type')}/{gold.get('status')}")
    return "FOUND", "an event involving the name matches the gold type/status" + note


# ------------------------------------------------------------------ analysis

def explain(gold: dict[str, Any], filings: list[dict[str, Any]], *, extractor, provider,
            passages_per_filing: int = 3) -> list[dict[str, Any]]:
    names = name_variants(gold)
    rows = []
    for filing in filings:
        passages = find_passages(filing["raw_text"], names, limit=passages_per_filing)
        if not passages:
            continue
        sections = filing.get("sections") or []
        for passage in passages:
            region = next((s for s in sections if _contains(s["text"], passage)), None)
            text = region["text"] if region else passage
            parsed = provider._parse_filing_section(text, region.get("item") if region else None)
            votes = backend_view(extractor, text, names)
            v, why = verdict_for(
                in_region=region is not None, votes=votes, threshold=extractor.threshold,
                fused_orgs=parsed["fused"].get("orgs", []), events=parsed.get("raw_events", []),
                gold=gold, names=names)
            rows.append({
                "accession": filing.get("accession"), "form": filing.get("form"),
                "filing_date": filing.get("filing_date"), "in_region": region is not None,
                "passage": passage, "verdict": v, "why": why, "backends": votes,
                "fused_org_votes": {o: w for o, w in parsed["fused"].get("org_votes", {}).items()
                                    if any(n.casefold() in o.casefold() for n in names)},
                "events_involving_name": [
                    {k: e.get(k) for k in ("event_type", "status", "subject", "object", "extraction_rule")}
                    for e in parsed.get("raw_events", [])
                    if any(same_company(e.get(r), names) for r in ("subject", "object"))],
                "verbs_in_passage": sorted(set(re.findall(
                    r"\b(acquir\w*|complet\w*|agree\w*|merg\w*|purchas\w*|bought|enter\w* into|announc\w*|clos\w*)\b",
                    passage, re.I))),
            })
    return rows


def _contains(region_text: str, passage: str) -> bool:
    # A passage is whitespace-joined sentences from the same document, so a
    # normalized-prefix check is robust to line-wrap differences.
    norm = lambda s: re.sub(r"\s+", " ", s)  # noqa: E731
    return norm(passage)[:200] in norm(region_text)


def summarize(rows: list[dict[str, Any]]) -> dict[str, int]:
    counts = {v: 0 for v in VERDICTS}
    for r in rows:
        counts[r["verdict"]] += 1
    return {k: v for k, v in counts.items() if v}


def render_markdown(gold: dict[str, Any], rows: list[dict[str, Any]]) -> str:
    names = name_variants(gold)
    lines = [f"# Miss explanation: {gold.get('counterparty') or names[0]}",
             f"Gold: {gold.get('event_type')}/{gold.get('status')} ~{gold.get('approx_date')}",
             f"Verdict counts across passages: {summarize(rows) or 'no passages found'}", ""]
    for r in rows:
        lines += [f"## {r['form']} {r['accession']} ({r['filing_date']}) -- {r['verdict']}",
                  f"_{r['why']}_", "",
                  "> " + r["passage"][:1500].replace("\n", " "), "",
                  f"- in located region: {r['in_region']}",
                  f"- verbs in passage: {', '.join(r['verbs_in_passage']) or 'none'}",
                  f"- fused org votes for the name: {r['fused_org_votes'] or 'none'}"]
        for b, v in r["backends"].items():
            lines.append(f"- backend {b} (weight {v['weight']}): {v['orgs_matching_name'] or 'did not produce the name'}")
        lines.append(f"- events involving the name: {r['events_involving_name'] or 'none'}")
        lines.append("")
    return "\n".join(lines)


# --------------------------------------------------------------------- I/O

def cached_get_text(cache_dir: Path, get_text: Callable = _get_text) -> Callable:
    cache_dir.mkdir(parents=True, exist_ok=True)

    def fetch(url: str, user_agent: str) -> str:
        path = cache_dir / (hashlib.sha1(url.encode()).hexdigest() + ".txt")
        if path.exists():
            return path.read_text(encoding="utf-8")
        text = get_text(url, user_agent)
        path.write_text(text, encoding="utf-8")
        return text
    return fetch


def _pick_events(gold: dict[str, Any], needle: str) -> list[dict[str, Any]]:
    n = needle.casefold()
    return [e for e in gold.get("events", [])
            if n == str(e.get("id", "")).casefold()
            or any(n in v.casefold() for v in name_variants(e))]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--company")
    ap.add_argument("--counterparty", help="gold event id, or part of a counterparty/alias name")
    ap.add_argument("--study", type=Path, default=ROOT / "data/eval_study/ma_saturation_pilot_v1.json")
    ap.add_argument("--gold-dir", type=Path, default=ROOT / "data/eval_gold")
    ap.add_argument("--user-agent")
    ap.add_argument("--start", default="2015-01-01")
    ap.add_argument("--end", default="2026-12-31")
    ap.add_argument("--out-dir", type=Path, default=ROOT / "data/diagnostics")
    ap.add_argument("--cache-dir", type=Path, default=ROOT / ".helix_cache/edgar")
    ap.add_argument("--text-file", type=Path, help="analyze a saved document instead of downloading")
    ap.add_argument("--names", help="comma-separated names (with --text-file)")
    a = ap.parse_args(argv)

    provider = EdgarMAExpansionProvider(fetch_filings_fn=lambda _: {})
    extractor = provider.extractor

    jobs: list[tuple[dict[str, Any], list[dict[str, Any]]]] = []
    if a.text_file:
        if not a.names:
            ap.error("--text-file needs --names")
        raw = a.text_file.read_bytes().decode("utf-8", "replace")
        text = strip_html(raw, unwrap_source_lines=True) if "<" in raw[:2000] else raw
        filing = {"accession": a.text_file.name, "form": "FILE", "filing_date": "",
                  "raw_text": text, "sections": locate_ma_regions(text, form="FILE")}
        names = [n.strip() for n in a.names.split(",") if n.strip()]
        jobs = [({"counterparty": n, "aliases": [], "id": n}, [filing]) for n in names]
    else:
        if not (a.company and a.counterparty and a.user_agent):
            ap.error("give --company, --counterparty and --user-agent (or use --text-file)")
        spec = company_spec(load_json(a.study), a.company)
        gold = load_json(a.gold_dir / f"{a.company}.json")
        events = _pick_events(gold, a.counterparty)
        if not events:
            raise SystemExit(f"No gold event matches {a.counterparty!r}")
        cik = spec.get("cik")
        if not cik:
            raise SystemExit("study entry has no cik; add one or resolve it first")
        fetch = cached_get_text(a.cache_dir)
        _, filings, errors = collect_audit_filings(cik, a.user_agent, start=a.start, end=a.end, get_text_fn=fetch)
        if errors:
            print(f"warning: {len(errors)} filing(s) failed to download", file=sys.stderr)
        jobs = [(e, filings) for e in events]

    a.out_dir.mkdir(parents=True, exist_ok=True)
    for gold_event, filings in jobs:
        rows = explain(gold_event, filings, extractor=extractor, provider=provider)
        report = render_markdown(gold_event, rows)
        slug = re.sub(r"[^a-z0-9]+", "_", str(gold_event.get("id") or gold_event.get("counterparty")).lower()).strip("_")
        (a.out_dir / f"{slug}.md").write_text(report, encoding="utf-8")
        print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
