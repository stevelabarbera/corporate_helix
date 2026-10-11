#!/usr/bin/env python3
"""
Write an EDGAR coverage manifest for one company (metadata only; see
providers/edgar_coverage.py).

  python3 code/eval/coverage_manifest.py --cik 2095096 --user-agent "Name email@example.com"
  python3 code/eval/coverage_manifest.py --submissions-json CIK0002095096.json   # offline

Needs sec.gov access unless --submissions-json is given. Older paginated pages
are fetched only when they overlap the window.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from providers import edgar_resolver as er
from providers.edgar_coverage import build_manifest, render_markdown, summarize_pages


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cik")
    ap.add_argument("--user-agent")
    ap.add_argument("--submissions-json", help="a saved submissions JSON (skips the network)")
    ap.add_argument("--start", default="2015-01-01")
    ap.add_argument("--end", default="2026-12-31")
    ap.add_argument("--out-dir", default="data/coverage")
    a = ap.parse_args(argv)

    if a.submissions_json:
        raw = json.loads(Path(a.submissions_json).read_text(encoding="utf-8"))
        merged = raw
        if raw.get("filings", {}).get("files"):
            print("note: offline mode does not fetch older pages; they are listed but not merged", file=sys.stderr)
    elif a.cik and a.user_agent:
        cik10 = str(int(a.cik)).zfill(10)
        raw = er._get_json(f"{er.SEC_DATA}/submissions/CIK{cik10}.json", a.user_agent)
        merged = er._merge_older_submission_pages(raw, a.user_agent, start=a.start, end=a.end)
    else:
        ap.error("give --submissions-json, or both --cik and --user-agent")

    manifest = build_manifest(merged, start=a.start, end=a.end,
                              pages=summarize_pages(raw, start=a.start, end=a.end))
    out = Path(a.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    stem = f"cik{str(manifest['cik'] or a.cik).zfill(10)}"
    (out / f"{stem}.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (out / f"{stem}.md").write_text(render_markdown(manifest), encoding="utf-8")
    print(render_markdown(manifest))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
