#!/usr/bin/env python3
"""
Pre-demo audit: list every OFFICIAL_WEBSITE declaration in a domain
observations file for quick human eyeballing before a live presentation.

This does NOT replace running the actual iterative expansion / domain
discovery against real GLEIF data -- it's a fast last-mile check on
whatever observations file you already have, so you can catch an
unlisted third-party site before it shows up as an AUTO/HIGH domain on
someone else's screen.

Usage:
    python3 audit_official_declarations.py path/to/*_domain_observations.json [...]

For each OFFICIAL_WEBSITE observation found, prints the entity, the
domain, and the declaration reason, sorted by domain so look-alike or
suspicious groupings are easy to spot. Domains already covered by the
known third-party reference denylist (providers/official_site.py) are
called out explicitly, since if one of THOSE still shows up here it
means the observations file predates this fix and should be regenerated.
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from providers.official_site import _is_third_party_reference_domain  # noqa: E402


def load_observations(path: str) -> list[dict]:
    data = json.loads(Path(path).read_text())
    if isinstance(data, dict):
        data = data.get("observations", [])
    return data


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 1

    rows = []
    for path in sys.argv[1:]:
        for obs in load_observations(path):
            if obs.get("evidence_type") != "OFFICIAL_WEBSITE":
                continue
            rows.append({
                "source_file": path,
                "domain": obs.get("domain"),
                "entity_name": obs.get("entity_name"),
                "reference": obs.get("reference"),
                "declaration_reason": (obs.get("raw") or {}).get("declaration_reason"),
            })

    if not rows:
        print("No OFFICIAL_WEBSITE declarations found in the given file(s).")
        return 0

    rows.sort(key=lambda r: (r["domain"] or ""))

    print(f"{len(rows)} OFFICIAL_WEBSITE declaration(s) across {len(sys.argv) - 1} file(s)\n")
    flagged = 0
    for r in rows:
        stale_flag = ""
        if _is_third_party_reference_domain(r["domain"] or ""):
            stale_flag = "  <-- ON DENYLIST: regenerate this observations file with the current fix"
            flagged += 1
        print(f"{r['domain']:35s} | {r['entity_name']}{stale_flag}")
        print(f"    reason: {r['declaration_reason']}")
        print(f"    ref   : {r['reference']}\n")

    print("-" * 72)
    if flagged:
        print(f"{flagged} entrie(s) are on the known-bad denylist -- this data predates "
              f"the fix. Regenerate before presenting.")
    else:
        print("None matched the known denylist. Eyeball the domains above yourself "
              "for anything that looks like an aggregator/directory/encyclopedia "
              "site NOT on the denylist -- that's the known open gap this fix "
              "does not cover.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
