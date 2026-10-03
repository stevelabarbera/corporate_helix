# Corporation Helix — GLEIF Decisions Log

Mirrors the format of `docs/DECISIONS_EDGAR_MA.md`: one ADR per real
architectural decision or bug fix on the GLEIF side, in chronological
order, each self-contained enough that neither a human nor a future AI
session has to reconstruct the reasoning from chat history.

---

## ADR-GLEIF-001 — M4.2 auto-enrichment was built correctly but never wired into the CLI; fixed and validated against real LEIs

**Date:** 2026-09-25 (re-applied 2026-09-29 after an earlier delivery of
this fix was never merged — see note at the end)
**Status:** Accepted

### Context

M4.2's stated goal (per `CORPORATION_HELIX_CONTEXT_2026-08-28.md` and
prior session notes) was: wire `data/processed/gleif_lei.sqlite` directly
into the Level 2 RR canonicalization path so child/parent LEIs are
auto-enriched from the local index, removing the need for manual
`--child-name`/`--parent-name` flags. Two commits (`b8535f9 M4.2 add
automatic GLEIF RR Level 1 enrichment`, `9e0da96 work on 4.2`) already
existed claiming this was done.

Before treating M4.2 as complete, attempted to validate it against real
data (real Dokobit/Signicat LEIs confirmed to exist in the local GLEIF
Level 1 index during a separate investigation into private-company M&A
coverage gaps — see `CORPORATION_HELIX_CONTEXT_2026-08-28.md`'s "Known
coverage gap" section). Don't trust a git log message or a
synthetic-placeholder test as proof a capability actually works — run it
against something real.

### What was actually found

`python3 code/canonicalize_gleif_rr.py ...` failed immediately with:

```
ModuleNotFoundError: No module named 'providers.gleif_lei_lookup'
```

Not a subtle logic bug — the auto-enrichment path could not run at all,
on any input, ever, since the commit that supposedly added it.

Tracing it down: the real M4.2 logic *did* exist, correctly written, as a
matched pair of files — `code/gleif_rr_adapter.py` (with a proper
`_resolve()` method implementing the intended precedence: explicit
override → SQLite index lookup → `UNRESOLVED_RETRY`) and
`code/gleif_lei_lookup.py` (the `GleifLeiIndex` class itself) — added
together in commit `9e0da96`, correctly cross-referencing each other via
a relative import (`from .gleif_lei_lookup import ...`). But both files
were loose at the top level of `code/`, not inside `code/providers/`.
Meanwhile `code/providers/gleif_rr_adapter.py` — the file
`canonicalize_gleif_rr.py`'s CLI actually imports — was a **stale,
pre-M4.2 copy** with no `lei_index` parameter, no lookup logic, and no
knowledge that the new files even existed.

In short: the M4.2 work was done correctly, in the right shape, with the
right logic — and then never connected to the thing that actually runs.
This is why the only existing test
(`tests/test_gleif_rr_vertical_slice.py`) never caught it: that test
always supplies manual `--name`/`--jurisdiction`-equivalent overrides,
which bypass index lookup entirely by design (overrides are meant to win
over the index). It was testing override precedence, never the
auto-enrichment path itself — so a complete `ModuleNotFoundError` in the
auto-enrichment code path had zero chance of surfacing in CI.

### Decision

- Moved both files into `providers/` with `git mv` (preserving history):
  `providers/gleif_lei_lookup.py`, `providers/gleif_rr_adapter.py`.
- Deleted the stale pre-M4.2 copy that had been sitting in `providers/`.
- Verified end-to-end against real data: built a real-schema SQLite
  fixture (same columns as `build_gleif_lei_index.py` produces) seeded
  with Dokobit UAB (`8945002COKCH510PDI59`, Lithuania) and Signicat AS
  (`636700GM6DEIS5MBAV78`, Norway) — both confirmed present and `ACTIVE`
  in the real local GLEIF Level 1 index — and ran the same relationship
  record two ways: once with manual name/jurisdiction overrides (the old
  workflow) and once with zero manual flags, relying purely on the
  SQLite auto-lookup. Both produced identical resolved names,
  jurisdictions, and relationship predicates.
- Also verified the miss case: an LEI not present in the index correctly
  returns `UNRESOLVED_RETRY` with the bare LEI kept visible as the
  display value — never an invented name — matching the module's own
  stated design contract.
- Added `tests/test_gleif_rr_auto_enrichment.py` (4 tests) as the first
  real coverage of the auto-enrichment path itself.

### Consequence

M4.2 is now genuinely done and proven, not just committed. The fix is a
file-location/wiring correction only — no change to the actual
resolution logic, since that logic was already correct once it could be
reached. `canonicalize_gleif_rr.py` run without `--name`/`--jurisdiction`
flags now correctly auto-enriches from the local Level 1 index, which
unblocks M4.3 (arbitrary RR records → canonical graph → ASM seed,
generalized beyond the one hand-picked SentinelOne case) from being built
on top of a capability that was never actually functional.

One thing this ADR does **not** validate: whether the *historical*
SentinelOne benchmark ("21 nodes, 20 relationships, 0 merges, 1 review
candidate", referenced in `CORPORATION_HELIX_CONTEXT_2026-08-28.md`
section 7/section on GLEIF regression) still holds under the fixed
auto-enrichment path specifically. No raw RR-shaped fixture or runnable
script reproducing that exact benchmark was found in the repo during this
session — it exists only as prose in the context doc. If that number
matters going forward (e.g. as a regression gate before M4.3), it should
be reconstructed as a real, checked-in fixture and test rather than left
as historical prose, since prose isn't something CI can catch a
regression against.

### Note on re-application (2026-09-29)

This fix was originally built and bundled on 2026-09-25, but the bundle
was never pulled into the working repo before a multi-day gap in the
session. By 2026-09-29, `main` had moved forward with real, unrelated
EDGAR work (merger-agreement party-list parsing, Exhibit 21 subsidiary
extraction, Target Corp historical filings) but still had the exact same
broken GLEIF import — confirmed by searching every branch on the remote,
not just `main`. Re-applied cleanly on top of the then-current `main`
with no changes to the fix itself. Two other remote branches
(`demo-readiness-root-resolution`, `fix/merge-arbitration-psl-domain-repo-hygiene`)
were checked during this investigation and found to already be fully
merged into `main` — stale leftover refs, not hidden unmerged work.
