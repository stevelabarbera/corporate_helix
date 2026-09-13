#!/usr/bin/env python3
"""
M3.8.5 EDGAR M&A benchmark.

The production extractor lives in parsers.edgar_ma_extractor. This benchmark
imports that implementation so benchmark and production behavior cannot drift.
"""
import argparse
import json
import time
from pathlib import Path

from parsers.edgar_ma_extractor import (
    RegexBackend,
    SpacyBackend,
    LegalRulesBackend,
    fuse,
    infer_events,
    completed_only,
    ekey,
)


def prf(pred, gold):
    p = set(pred)
    g = set(gold)
    tp = len(p & g)
    fp = len(p - g)
    fn = len(g - p)
    precision = tp / (tp + fp) if tp + fp else (1.0 if not g else 0.0)
    recall = tp / (tp + fn) if tp + fn else 1.0
    f1 = (2 * precision * recall / (precision + recall)) if precision + recall else 0.0
    return {"tp": tp, "fp": fp, "fn": fn, "precision": precision, "recall": recall, "f1": f1}


def load_sections(paths):
    out = {}
    for p in paths:
        raw = json.loads(Path(p).read_text(encoding="utf-8"))
        for f in raw.get("filings", []):
            for s in f.get("sections", []):
                out[(f.get("accession"), s.get("item"))] = {
                    "text": s.get("text", ""),
                    "filing_date": f.get("filing_date"),
                    "company": raw.get("company"),
                }
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gold", default="./data/benchmark/legal_benchmark_gold_v385.json")
    ap.add_argument("--inputs", nargs="+", required=True)
    ap.add_argument("--spacy-model", default="en_core_web_sm")
    ap.add_argument("--threshold", type=float, default=1.5)
    ap.add_argument("--json-out")
    a = ap.parse_args()

    # Benchmark remains strict. Unlike the historical production provider,
    # it does not silently fall back to a different ensemble.
    sp = SpacyBackend(a.spacy_model)
    backends = [RegexBackend(), sp, LegalRulesBackend()]
    weights = {"regex": 0.5, "spacy": 1.0, "legal_rules": 1.25}

    sections = load_sections(a.inputs)
    gold = json.loads(Path(a.gold).read_text(encoding="utf-8"))

    orgm, aliasm, eventall, eventpos = [], [], [], []
    neg = negfp = 0
    rows = []
    start = time.perf_counter()

    for case in gold["cases"]:
        sec = sections[(case["accession"], case["item"])]
        text = sec["text"]
        outputs = {b.name: b.parse(text) for b in backends}
        fused = fuse(outputs, weights, a.threshold)
        raw_events = infer_events(text, fused["aliases"], fused["orgs"], case["item"])
        final_events = completed_only(raw_events)

        om = None
        if case["expected_orgs"]:
            om = prf(fused["orgs"], case["expected_orgs"])
            orgm.append(om)
        am = prf(list(fused["aliases"].items()), list(case["expected_aliases"].items()))
        aliasm.append(am)
        em = prf(
            [ekey(x) for x in final_events],
            [ekey(x) for x in case["expected_events"]],
        )
        eventall.append(em)
        if case["expected_events"]:
            eventpos.append(em)
        else:
            neg += 1
            if final_events:
                negfp += 1

        rows.append({
            "case": case["id"],
            "org": om,
            "alias": am,
            "event": em,
            "raw_events": raw_events,
            "completed_events": final_events,
            "fused": fused,
        })
        print(
            f"{case['id']}: org={(om['f1'] if om else 0):.2f} "
            f"alias={am['f1']:.2f} event={em['f1']:.2f} "
            f"raw={len(raw_events)} completed={len(final_events)} "
            f"proposed={sum(1 for e in raw_events if e['status'] == 'PROPOSED')}"
        )

    macro = lambda xs: sum(x["f1"] for x in xs) / len(xs) if xs else 0.0
    summary = {
        "org_macro_f1": macro(orgm),
        "alias_macro_f1": macro(aliasm),
        "event_macro_f1_all": macro(eventall),
        "event_macro_f1_positive_only": macro(eventpos),
        "negative_control_fp_rate": negfp / neg if neg else 0.0,
        "runtime_seconds": time.perf_counter() - start,
    }

    print("\nM3.8.5 SUMMARY")
    for k, v in summary.items():
        print(f"{k}: {v:.3f}")

    if a.json_out:
        Path(a.json_out).parent.mkdir(parents=True, exist_ok=True)
        Path(a.json_out).write_text(
            json.dumps({"summary": summary, "cases": rows}, indent=2),
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
