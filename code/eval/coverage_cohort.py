#!/usr/bin/env python3
"""
Run the EDGAR coverage manifest for every company in the saturation cohort and
print one aggregate table (which deal-relevant forms are skipped, per company
and in total). Metadata only; needs sec.gov access.

  python3 code/eval/coverage_cohort.py --user-agent "$SEC_USER_AGENT"

CIKs come from the frozen result files in data/eval_study/ma_saturation_results/
(read only; nothing there is modified).
"""
from __future__ import annotations

import argparse
import glob
import json
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from providers import edgar_resolver as er
from providers.edgar_coverage import SKIP_UNSUPPORTED_DEAL, build_manifest, render_markdown, summarize_pages


def cohort_ciks(results_dir: str) -> list[tuple[str, str]]:
    out = []
    for p in sorted(glob.glob(str(Path(results_dir) / "*.json"))):
        d = json.loads(Path(p).read_text(encoding="utf-8"))
        if d.get("cik"):
            out.append((d.get("company") or Path(p).stem, str(d["cik"])))
    return out


def manifest_for(cik: str, user_agent: str, start: str, end: str) -> dict:
    cik10 = str(int(cik)).zfill(10)
    raw = er._get_json(f"{er.SEC_DATA}/submissions/CIK{cik10}.json", user_agent)
    merged = er._merge_older_submission_pages(raw, user_agent, start=start, end=end)
    return build_manifest(merged, start=start, end=end, pages=summarize_pages(raw, start=start, end=end))


def aggregate(manifests: dict[str, dict]) -> str:
    skipped = {n: Counter(r["form"] for r in m["rows"] if r["disposition"] == SKIP_UNSUPPORTED_DEAL)
               for n, m in manifests.items()}
    total = Counter()
    for c in skipped.values():
        total.update(c)
    forms = [f for f, _ in total.most_common()]
    lines = ["# Skipped deal-relevant forms across the cohort", "",
             "| company | retrievable / in-window | " + " | ".join(forms) + " |",
             "|---|---|" + "---|" * len(forms)]
    for n, m in manifests.items():
        t = m["totals"]
        lines.append(f"| {n} | {t['retrievable']} / {t['in_window']} | "
                     + " | ".join(str(skipped[n].get(f, 0)) for f in forms) + " |")
    lines.append("| **TOTAL** | | " + " | ".join(f"**{total[f]}**" for f in forms) + " |")
    flagged = [f"- {n}: {f}" for n, m in manifests.items() for f in m["flags"] if "NOTHING" in f or "no item" in f]
    return "\n".join(lines + ["", "## Other flags", *(flagged or ["- none"])]) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--user-agent", required=True)
    ap.add_argument("--results-dir", default="data/eval_study/ma_saturation_results")
    ap.add_argument("--start", default="2015-01-01")
    ap.add_argument("--end", default="2026-12-31")
    ap.add_argument("--out-dir", default="data/coverage")
    ap.add_argument("--delay", type=float, default=0.3, help="seconds between companies")
    a = ap.parse_args(argv)

    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    manifests = {}
    for name, cik in cohort_ciks(a.results_dir):
        print(f"... {name} ({cik})", file=sys.stderr)
        m = manifest_for(cik, a.user_agent, a.start, a.end)
        manifests[name] = m
        stem = f"cik{str(cik).zfill(10)}"
        (out / f"{stem}.json").write_text(json.dumps(m, indent=2), encoding="utf-8")
        (out / f"{stem}.md").write_text(render_markdown(m), encoding="utf-8")
        time.sleep(a.delay)
    report = aggregate(manifests)
    (out / "cohort_summary.md").write_text(report, encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
