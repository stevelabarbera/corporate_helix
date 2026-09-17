# CONTEXT ADDENDUM — Tesla Test Pass

**Date:** 2026-09-16

Part of the EDGAR M&A historical context. Keep alongside
`CONTEXT_EVENT_EXTRACTION.md`, `CONTEXT_EVENT_EXTRACTION_HARDENING.md`,
`CONTEXT_EVENT_EXTRACTION_SIX_FLAGS.md`,
`CONTEXT_EVENT_EXTRACTION_PARAMOUNT.md`,
`CONTEXT_EVENT_EXTRACTION_BRINKER.md`, `CONTEXT_EVENT_EXTRACTION_FORD.md`,
and `CONTEXT_EVENT_EXTRACTION_GAZETTEER.md`.

## Why this pass happened

Fifth untested company. Picked SolarCity deliberately as a generalization
check as much as a fresh test: same "entered into an Agreement and Plan
of Merger" phrasing already fixed for Lumen, same multi-party-with-shell
structure (Tesla, SolarCity, D Subsidiary, Inc.) already fixed for Six
Flags. Confirmed clean on the announcement text -- and then surfaced a
real bug on the closing text, plus a bigger, still-open architectural
question worth being precise about.

## Bug 7 — FIXED: ACQUIRED pattern's acquirer/target resolution never consulted aliases

The real closing 8-K's Item 2.01 text, in isolation, produced zero events:
"Tesla completed its previously announced acquisition of SolarCity" --
"Tesla" and "SolarCity" are only ever short aliases in this text (no
corporate suffix, no parenthetical definition anywhere in the section).
`known_prefix()`, which the `ACQUIRED`/"completed acquisition of"
pattern's target resolution relied on exclusively, only matches full org
names -- never resolves through the `aliases` dict at all. This is the
same bug shape already fixed once, at a different call site: the 10-K
declarative pattern (`we acquired X`) already had an alias-resolution
fallback (`resolve(raw, aliases)`), built and validated for Tenable, but
it was never applied to the two other `known_prefix()` call sites
(`AGREED_TO_ACQUIRE`'s target resolution, and this `ACQUIRED` pattern).

**Fix:** applied the same, already-established `resolve(raw, aliases)`
fallback to this pattern's target resolution. Also fixed acquirer (`acq`)
resolution the same way -- but carefully: an initial attempt to capture
the acquirer subject via a generic capturing group immediately before
"completed" (`([A-Z][\\w&.,' -]{1,80}?)\\s+completed`) caused a real
regression (confirmed via the full suite): it swallowed leading date/
preamble text ("On November 1, 2017, CenturyLink, Inc." instead of just
"CenturyLink, Inc.") on the existing, already-passing Lumen test, because
non-greedy quantifiers still let the engine choose the earliest possible
match start. Replaced with a safer, non-capturing-group approach: check
which known org OR alias sits at an **exact adjacent suffix** of the text
immediately before "completed" (`before.endswith(candidate)`), which
can't over-match the way a generic character class can. Full suite: 223
after the first (reverted) attempt's one failure, confirmed clean at 223
again after the fix. Verified directly against the real isolated closing
text with aliases artificially present (confirms the fix works once
aliases exist for a given parse call) and against the existing Lumen/
Cisco/Disney test cases (confirms no regression).

## Not fixed — the deeper, real finding: full legal names are often never restated at all across a deal's later filings

Even with the fix above, the **real** closing 8-K -- both its own
sections, Item 1.01 (about note indentures) and Item 2.01 (the
completion notice) -- still produces **zero events** in true isolation.
Confirmed directly. Root cause: neither section anywhere restates
"Tesla Motors, Inc." or "SolarCity Corporation" in full. Those names were
established exactly once, months earlier, in the entirely separate
announcement 8-K accession. The alias-resolution fix above only helps
once an alias mapping already exists for the text being parsed -- it
can't invent one from nothing.

**This is likely a bigger deal than it looks for one company.** Defining
full legal names once (in the announcement) and using only short aliases
in every subsequent filing about the same deal -- the closing 8-K, 8-K/A
amendments, 10-Qs, 10-Ks -- is completely standard, ordinary SEC drafting
practice, not a Tesla-specific quirk. This may well be a contributing
cause behind several already-recorded `NOT_DISCOVERED` misses on other
companies (Lumen's divestitures, Disney's Fox events, several of
Tenable's acquisitions) -- worth treating as a hypothesis to check
specifically, not an established fact, since each of those misses hasn't
been individually re-diagnosed against this specific cause.

**Recommended fix direction, not attempted this pass:** the cleanest fix
is probably not "thread aliases across sections/filings" (fragile, order-
dependent, and the real closing 8-K's own sections don't have the aliases
either -- there's nothing to thread from within that filing at all).
Instead, generalize the existing `REGISTRANT_SELF_REFERENCE` mechanism
(already built for "we acquired X", used without needing the registrant's
name spelled out anywhere in the text): the caller of `parse_section`
**already knows** the registrant's real name and CIK, independent of
parsing the item text at all -- that's literally what was used to fetch
the filing. Passing that known identity into `infer_events` as a trusted
"self" hint would let "Tesla completed its acquisition of X" resolve
"Tesla" as the registrant itself, the same way "we acquired X" already
does, without needing the full name to appear in the text being parsed at
all. This is real design work (threading a new parameter through
`parse_section`/`infer_events`, deciding how to safely match a short
company nickname against the known registrant name in general) --
appropriately scoped as its own dedicated pass, not squeezed into this
one on top of everything else found this session.

## A scoring nuance worth being precise about

The coverage harness's own run shows Tesla at 1/2, with `tesla-2`
(`ACQUIRED`/COMPLETED) marked `EVENT_TYPE_MISMATCH` rather than
`NOT_DISCOVERED` -- matched against a real `SUBSIDIARY_OF` event
(`SolarCity Corporation -> Tesla Motors, Inc.`, COMPLETED). Traced this
down precisely: that `SUBSIDIARY_OF` event comes from the
**announcement's own** Item 1.01 text ("...with SolarCity surviving the
Merger as a wholly owned subsidiary of Tesla"), which is forward-looking
language written in the announcement, not the actual closing
confirmation. It's a coincidental, same-direction match on the same two
real entities, not genuine recognition of the closing event described
above. Recorded here so this doesn't get mistaken for partial credit on
the actual bug just documented -- the real closing 8-K's own text still
produces nothing, full stop.

## New gold + raw fixtures

`data/eval_gold/tesla.json` -- 2 events (SolarCity announcement + closing),
scoped to the 2016 deal only; Tesla's other real acquisitions (Maxwell
Technologies 2019, Grohmann Engineering 2017) out of scope for this pass.
Gold blindness PARTIAL -- an M&A aggregator quoting 10-K/8-K exhibit text
appeared in the same search as the independent sources used to write the
record; the real 8-K text was fetched afterward, for diagnostic testing,
not to write gold.

`data/eval_raw/tesla_real.json` -- unlike the Six Flags/Ford fixtures,
this one deliberately includes BOTH the announcement and the closing 8-K,
since both are genuinely reachable under the live 1.01/2.01 item filter
(no item-filter gap here, unlike Six Flags' Item 5.02 or Ford's Item
7.01). The closing text's expected non-recall is a real, now-documented
extraction gap, not an unreachability issue -- correctly included rather
than omitted, so the coverage number reflects the real state of things.

## Current aggregate (6 companies with raw data; Brinker/Ford still skipped)

6/22 (27.3%), 95% CI [0.13, 0.48].

## How to resume

```bash
python3 -m pytest tests/                          # confirm 223/223
cd code/eval && python3 run_coverage_eval.py --gold lumen.json disney.json tenable.json six_flags.json paramount.json brinker.json ford.json tesla.json
```

Next candidate work, in priority order:
1. The registrant-self-reference generalization described above -- this
   is the single highest-leverage open item found this session, since it
   may explain misses across multiple already-tested companies, not just
   Tesla.
2. Re-diagnose Lumen's 3 divestiture misses and Disney's Fox misses
   specifically against this hypothesis, rather than assuming it applies.
3. Continue the untested-company list: AIG, Netflix.
