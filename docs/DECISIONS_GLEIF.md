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

---

## ADR-GLEIF-002 — M4.3C's domain-bridge CLI wiring was dropped as collateral damage from an unrelated patch; restored with a real loader this time

**Date:** 2026-09-29
**Status:** Accepted

### Context

After fixing ADR-GLEIF-001, re-validated the rest of the GLEIF milestone
chain in `CORPORATION_HELIX_CONTEXT.md`'s "UPDATED MILESTONE SNAPSHOT"
rather than trusting the `COMPLETE` labels at face value — the same
discipline that caught M4.2. M4.2B and M4.3B both held up exactly as
documented (M4.2B's temporal period-parsing matched real Desjardins data
exactly; M4.3B's domain-candidate output was byte-for-byte identical to
the committed Sony result on a fresh regeneration). M4.3C did not.

### What was actually found

The documented "Live Sony recursive-expansion checkpoint"
(`python3 code/run_iterative_company.py --company "Sony" --lei
529900R5WX9N2OI2N910 --domain-candidates
data/processed/sony_official_site_candidates.json`, expected: 3
iterations, 15 entities → 2 domains → 0, `Converged: True`) could not be
reproduced. The current script's `--help` has no `--domain-candidates`
flag at all, and `main()` only ever constructs a
`GleifCompanyExpansionProvider` — never a `DomainCandidateExpansionProvider`,
even though that class exists and is correctly implemented in
`expansion_bridges.py`.

Traced via `git log -p -- code/run_iterative_company.py`: the flag and
its wiring existed, and were removed in commit `f9dcd9a` ("Ran through
NTT as our new data identified a few bugs and new features"). That
commit was applied via `git apply` from a patch file
(`README_M43D_INTEGRATION.txt` describes it) whose own stated purpose was
wiring `root_entity_resolver` into `helix_company.py` — a different
feature, addressing the Sony/NTT name-resolution gap from an earlier
section. The same commit also substantially rewrote `expansion_bridges.py`
(+304 lines) in the same pass, and the domain-bridge CLI wiring was
silently dropped as a side effect. No test existed to catch this — the
`COMPLETE / LIVE VALIDATED` status was a one-time manual run, documented
as prose in the context doc, with nothing to re-run automatically when
later commits touched the same files.

A second, smaller gap surfaced while restoring this: the original wiring
called `DomainCandidateExpansionProvider.from_json(args.domain_candidates)`,
but that classmethod does not exist on the *current*
`DomainCandidateExpansionProvider` — its constructor now takes a
`candidate_fn(pivot, iteration)` callable, not a file path. A straight
revert of the old diff would have failed on a different error, not
actually fixed anything. `domain_candidates.py`'s `write_json()` had no
reverse (`load_candidates()`) at all — the round-trip simply never
existed.

### Decision

- Restored `--domain-candidates` and the import of
  `DomainCandidateExpansionProvider` in `code/run_iterative_company.py`,
  rewritten to match the current constructor signature: load all
  candidates once via the new `load_candidates()`, group by
  `entity_lei`, and hand `run_expansion` a closure that returns the
  candidates matching whichever pivot it's currently expanding.
- Added `domain_candidates.load_candidates()` — the missing reverse of
  `write_json()` — reconstructing real `DomainCandidate` objects
  (enums included) from the JSON it writes.
- Restored the domain summary print lines (`Domains`, `Accepted domains`,
  `Review domains`, `Rejected domains`) that were removed in the same
  commit.
- Verified against the real saved Sony data
  (`data/processed/sony_official_site_candidates.json`): round-trips
  correctly through `load_candidates()`, and a reconstructed
  `DomainCandidateExpansionProvider` fed a fake pivot matching Sony
  Interactive Entertainment Europe's real LEI produces exactly the
  documented mapping — `DOMAIN / www.playstation.com / ACCEPTED / HIGH /
  pivot_eligible=True`, matching section 29.2's stated rule (`M4.3B AUTO
  + HIGH -> DOMAIN / ACCEPTED / HIGH / pivot eligible`) exactly.
- Added `tests/test_run_iterative_company_domain_bridge.py` (4 tests),
  including a subprocess-level `--help` check that asserts the flag
  itself is present — specifically so this exact "flag silently
  disappears during an unrelated refactor" failure mode can't happen a
  third time without a test catching it immediately.

### Consequence

The full documented 3-iteration Sony convergence result
(`--domain-candidates` end-to-end) still needs to be re-run against the
real local GLEIF Level 1/Level 2 indexes to fully close this out — this
session confirmed the *mechanism* is correct with real data, but the
sandbox used for this fix doesn't have the multi-GB real indexes
available to run the complete `run_iterative_company.py` invocation
end-to-end. That full re-run is the natural next step.

The broader lesson, now demonstrated twice in one evening (M4.2, M4.3C):
a `COMPLETE` label earned by one successful manual run, with no
accompanying automated test, is not durable against later unrelated
changes to shared files. Worth treating any future large patch-apply
(the `README_M43D_INTEGRATION.txt`-style workflow) as a trigger to
re-run every documented "known-good command" that touches the same
files, not just the one the patch was explicitly about.
