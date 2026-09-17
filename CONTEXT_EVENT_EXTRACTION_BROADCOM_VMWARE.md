# CONTEXT ADDENDUM — Broadcom/VMware Test Pass: CONVERTED_TO Was Hardcoded

**Date:** 2026-09-16

Part of the EDGAR M&A historical context. Keep alongside
`CONTEXT_EVENT_EXTRACTION.md`, `CONTEXT_EVENT_EXTRACTION_HARDENING.md`,
`CONTEXT_EVENT_EXTRACTION_DELL_EMC.md`,
`CONTEXT_EVENT_EXTRACTION_BAYER_MONSANTO.md`, and the other company
addenda from this session, plus `_GAZETTEER`.

## Why this pass happened

Eleventh company, third and final of the user's "beautiful use cases"
list: "the Multi-Tranche Platform Integration: Broadcom & VMware
(2022-2023)". Delivered exactly that: the real closing 8-K describes a
**four-step sequence** -- a First Merger, a mid-sequence Delaware
corp-to-LLC Conversion, a Second Merger, and a Third Merger -- across
**six named entities** (Broadcom, VMware, Verona Holdco Inc., Verona
Merger Sub Inc., Barcelona Merger Sub 2 Inc., Barcelona Merger Sub 3
LLC). The most structurally complex real closing text tested this
entire session.

## First result: everything resolved correctly (but one signal was suspicious)

```
ACQUIRED       Broadcom Inc. -> VMware, Inc.                          COMPLETED
MERGED_INTO    Verona Merger Sub, Inc. -> VMware, Inc.                COMPLETED
MERGED_INTO    Barcelona Merger Sub 2, Inc. -> Verona Holdco, Inc.    COMPLETED
MERGED_INTO    Verona Holdco, Inc. -> Barcelona Merger Sub 3, LLC     COMPLETED
SUBSIDIARY_OF  VMware, Inc. -> Verona Holdco, Inc.                    COMPLETED
SUBSIDIARY_OF  Verona Holdco, Inc. -> Broadcom Inc.                   COMPLETED
SUBSIDIARY_OF  Barcelona Merger Sub 3, LLC -> Broadcom Inc.           COMPLETED
CONVERTED_TO   VMware, Inc. -> Delaware limited liability company     COMPLETED
```

Every relationship is correct. But the last line was worth checking
carefully before declaring a clean win: this session already found one
case (Bug 10, Dell/EMC) where something that looked right turned out to
be a real bug, and `CONVERTED_TO` was a pattern this session hadn't
touched at all yet -- worth being suspicious of a clean first pass on an
untouched pattern, not just accepting it.

## Bug 15 — FIXED: CONVERTED_TO was hardcoded to "VMware" specifically, not general at all

Checked the actual code: `if conv and "VMware" in aliases:` -- the
pattern **only fires when the literal string "VMware" is a known
alias**, full stop. It was built for an earlier, unrelated VMware
corporate-conversion case (visible in the codebase from before this
session). It "worked" on this new Broadcom/VMware deal purely because
VMware happens to be the entity involved in *both* cases -- coincidence,
not generalization. Confirmed directly: on a synthetic test with a
completely different company name doing the exact same kind of
conversion, the old code produced nothing at all.

**Fix:** resolve the conversion's actual subject from the surrounding
text -- specifically the "`[Entity]` continuing as the surviving
corporation...(the '`[Alias]`')" construction that real merger-sequence
text uses right before describing the conversion (real Broadcom text:
"...VMware continuing as the surviving corporation in the First Merger
(the 'Surviving Company')...the Surviving Company was converted from a
Delaware corporation..."). The old VMware-specific check is kept only as
a fallback, so nothing regresses for the original use case if the
broader match ever fails to find a survivor clause.

**Verified as genuinely general, not just re-confirmed on VMware again:**
a synthetic test using an entirely made-up company ("Zephyr Corp.", no
VMware anywhere) now correctly produces
`CONVERTED_TO(Zephyr Corp. -> Delaware limited liability company)`.
The original VMware case still works too (separate regression test).
Full suite: 236/236 (234 baseline + 2 new tests). Verified through the
real Broadcom text too -- same correct result as before, but now via the
general path, confirmed by checking which branch actually fired.

This is a different kind of finding than most of this session: not a
missing pattern or a phrasing gap, but a pattern that looked correct and
even passed its own test, while secretly only working for one specific
company by name. Worth keeping in mind for any future pattern audit --
"does this generalize" is a real question worth asking even when a
pattern already appears to work, not just when it visibly fails.

## A scoring nuance, not an extraction bug

The eval harness shows Broadcom at 0/2, which looks alarming given the
system's output above is entirely correct. Traced it down precisely:
`coverage_harness.py`'s `score_company()` processes gold events **in
file order**, and for each one, greedily claims whichever system event
shares the same counterparty identity -- even reporting it as
`EVENT_TYPE_MISMATCH` when the types don't actually match -- removing it
from the pool for subsequent gold events. Since this fixture only
contains the closing text (no announcement), there's exactly one real
system event (`ACQUIRED`), which is a perfect match for `avgovmw-2`
(the closing) but gets greedily consumed by `avgovmw-1` (the
announcement, processed first) instead, leaving nothing for `avgovmw-2`
and producing a misleading `EVENT_TYPE_MISMATCH` + `NOT_DISCOVERED`
split rather than the honest `0/1 + 1/1` picture. Confirmed this is
pre-existing scorer behavior, not something introduced this pass, and
not unique to this fixture -- it would happen for any company with two
gold events sharing a counterparty where only one is actually reachable
by the raw text. A real, legitimate candidate for a scorer improvement
(type-aware bipartite matching instead of greedy sequential-by-
counterparty consumption), separate from anything about extraction
correctness.

## New gold + raw fixtures

`data/eval_gold/broadcom_vmware.json` -- 2 events (announced 2022-05-26,
closed 2023-11-22). Gold blindness PARTIAL -- several real, verbatim
8-K/10-Q/10-K excerpts appeared in the same search as Broadcom's own
press release; those excerpts were used afterward, deliberately, to
build and validate the fix.

`data/eval_raw/broadcom_vmware_real.json` -- only the closing (Item
2.01) 8-K. The announcement text was found via search but not in
complete form (cut off mid-sentence); not included rather than
fabricating the missing portion, same discipline as the Dell/EMC closing
fragment from two passes ago.

## Current aggregate (12 companies with raw data; Brinker/Ford still skipped)

10/32 (31.25%), 95% CI [0.18, 0.49] -- unchanged from before this
company given the scoring nuance above; the system's actual output for
Broadcom is fully correct.

## How to resume

```bash
python3 -m pytest tests/                          # confirm 236/236
cd code/eval && python3 run_coverage_eval.py --gold lumen.json disney.json tenable.json six_flags.json paramount.json brinker.json ford.json tesla.json aig.json netflix.json att.json dell_emc.json bayer_monsanto.json broadcom_vmware.json
```

This closes out the user's three-company "beautiful use cases" list
(Dell/EMC, Bayer/Monsanto, Broadcom/VMware) on top of the original
seven-company gamut -- twelve companies tested this session in total.

Next candidate work, in rough priority order:
1. **The scorer's greedy-matching limitation** -- worth fixing on its
   own merits now that it's been precisely diagnosed, independent of any
   specific company.
2. Everything already queued from prior addenda: the item-filter
   revisit, AT&T's and Bayer's real Reverse-Morris-Trust-style
   `DIVESTED_BUSINESS` shapes, the real GLEIF gazetteer validation pass,
   re-diagnosing Lumen's divestitures once real text for them is
   fetched.
3. A broader audit of other existing, untouched patterns (following this
   pass's lesson): are any other patterns secretly hardcoded to one
   specific company's name the way `CONVERTED_TO` was?
