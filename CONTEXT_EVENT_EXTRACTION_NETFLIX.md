# CONTEXT ADDENDUM — Netflix Test Pass (final company in original gamut)

**Date:** 2026-09-16

Part of the EDGAR M&A historical context. Keep alongside
`CONTEXT_EVENT_EXTRACTION.md`, `CONTEXT_EVENT_EXTRACTION_HARDENING.md`,
`CONTEXT_EVENT_EXTRACTION_SIX_FLAGS.md`,
`CONTEXT_EVENT_EXTRACTION_PARAMOUNT.md`,
`CONTEXT_EVENT_EXTRACTION_BRINKER.md`, `CONTEXT_EVENT_EXTRACTION_FORD.md`,
`CONTEXT_EVENT_EXTRACTION_TESLA.md`, `CONTEXT_EVENT_EXTRACTION_AIG.md`, and
`CONTEXT_EVENT_EXTRACTION_GAZETTEER.md`.

## Why this pass happened

Seventh and final company from the original untested list (Six Flags,
Chili's/Brinker, Paramount, Ford, Tesla, AIG, Netflix -- all seven now
done). Research turned up something far bigger than expected: a very
recent (December 2025), massive, and still-unfolding real transaction --
Netflix's $82.7B agreement to acquire Warner Bros. from Warner Bros.
Discovery, which was itself later overtaken by a rival Paramount Skydance
bid (confirmed via Wikipedia: Netflix withdrew in February 2026 when WBD's
board found Paramount's revised $110.9B offer superior).

## Result: a clean win, zero new bugs -- the right note to end the gamut on

This is, by a wide margin, the most structurally complex real transaction
tested this entire session -- more so than Paramount/Skydance:

- **A three-step structure**: a Holdco Merger under DGCL Section 251(g)
  (a technical parent-substitution mechanism), then WBD's internal
  separation of its Global Linear Networks business into a standalone
  SpinCo, then the actual Netflix-WBD merger itself.
- **Four real, named entities** in the preamble alone: Netflix, Inc.,
  Nightingale Sub, Inc. (Merger Sub), Warner Bros. Discovery, Inc., and
  New Topco 25, Inc. (Newco) -- one more than Paramount's already-complex
  five-entity structure had in its own preamble.
- **$82.7B enterprise value** -- the largest deal tested by a wide margin.

Despite all of that, the extractor resolved it correctly, with no new
fixes needed at all:

```
AGREED_TO_ACQUIRE  Netflix, Inc. -> Warner Bros. Discovery, Inc.  COMPLETED
MERGED_INTO        New Topco 25, Inc. -> Warner Bros. Discovery, Inc.  PROPOSED
MERGED_INTO        Nightingale Sub, Inc. -> Warner Bros. Discovery, Inc.  PROPOSED
SUBSIDIARY_OF      Warner Bros. Discovery, Inc. -> New Topco 25, Inc.  PROPOSED
SUBSIDIARY_OF      Warner Bros. Discovery, Inc. -> Netflix, Inc.  PROPOSED
```

Every fix made across this session's six earlier companies -- the shell-
exclusion logic (Six Flags, refined again for AIG), the multi-party
preamble handling (Six Flags), the generic legal-form entity pattern
(Paramount), the blank-line boundary fix (Ford), the alias-resolution
fallback (Tesla), the definitive-agreement modifier (AIG) -- all held up
together, simultaneously, on a transaction more complex than any of the
individual cases that produced them. That's a meaningful confirmation
that these were real, generalizable fixes and not narrow patches that
happened to work for one company each.

Verified against the real eval harness too: Netflix scores 1/1 (its one
scoped gold event), no regressions to any of the other seven companies'
scores. Aggregate across all 8 companies with raw data: 8/25 (32%, CI
[0.17, 0.52]).

## An important real-world complication, handled carefully in the gold file

This specific merger agreement did not survive: Paramount Skydance
launched a rival unsolicited tender offer on 2025-12-08, revised it
repeatedly, and on 2026-02-26 WBD's board determined Paramount's revised
offer was superior. Netflix declined to match and withdrew, letting
Paramount Skydance proceed as the winning bidder instead (this connects
directly to `paramount.json`'s own gold record from earlier in this
session, which already anticipated Paramount's pursuit of WBD).

The gold file's single event (`AGREED_TO_ACQUIRE`, `COMPLETED`) is scored
the same way this project has always scored that combination throughout
every other gold file: it means the agreement was genuinely *signed*, not
that the underlying merger ever closed -- the same convention used for
every `AGREED_TO_ACQUIRE`/COMPLETED event elsewhere. No `ACQUIRED`/closing
gold event was added, and unlike every other company's "closing not yet
fetched" situation in this project, there never will be one to add: the
merger never happened. Worth being explicit about this distinction so a
future reader doesn't mistake it for another instance of the item-filter
gap or an unfetched closing -- it's neither.

## New gold + raw fixtures

`data/eval_gold/netflix.json` -- 1 event, scoped to the Netflix-WBD
agreement only (2025-12-04). Gold blindness PARTIAL -- the initial
gaming-studio-history search was fully independent of any filing text,
but a follow-up search specifically about the WBD situation surfaced one
snippet of real 8-K text in a search result before the full text was
deliberately fetched for extraction testing.

`data/eval_raw/netflix_real.json` -- the Item 1.01 announcement only, by
necessity (no closing 8-K exists or ever will for this specific deal).

## Current aggregate (8 companies with raw data; Brinker/Ford still skipped)

8/25 (32%), 95% CI [0.17, 0.52].

## Where the "run the gamut" phase stands now

All seven originally-listed untested companies are done. Real, fixed
bugs found and verified across this phase: L.P. suffix gap, merger-of-
equals preamble/verb-tense gaps (Six Flags); suffix-less registrant names,
hardcoded agreement-name trigger (Paramount); blank-line entity-boundary
bleed (Ford); missing alias resolution in the ACQUIRED pattern (Tesla);
definitive-agreement modifier gap, shell-named-first target resolution,
a period-truncation bug (AIG). Real, confirmed-but-deliberately-not-fixed
structural gaps: the item-filter problem, now confirmed on four separate
real companies via four different item codes (Six Flags' 5.02, Brinker's
8.01, Ford's 7.01, AIG's 8.01); the missing 10-K/10-Q fetcher, which
alone accounts for Brinker's and Ford's entire misses; and the deeper
cross-filing alias-persistence question flagged in the Tesla pass
(recommended fix: generalize `REGISTRANT_SELF_REFERENCE` to a known-
registrant-identity hint, not yet attempted). One brand-new capability
built alongside all of this: the GLEIF gazetteer backend, opt-in and not
yet validated against the real 3.39M-row index.

## How to resume

```bash
python3 -m pytest tests/                          # confirm 227/227
cd code/eval && python3 run_coverage_eval.py --gold lumen.json disney.json tenable.json six_flags.json paramount.json brinker.json ford.json tesla.json aig.json netflix.json
```

Candidate next work, in rough priority order:
1. The item-filter revisit -- four real companies now, not an edge case.
2. Dig into why every `DIVESTED_BUSINESS` gold event has failed (Lumen's
   3, Disney's 1) -- still completely unexamined.
3. The registrant-self-reference generalization from the Tesla pass --
   still the single highest-leverage open item for cross-filing recall.
4. Run the real GLEIF gazetteer backend against the real 3.39M-row index
   and this session's real fixtures, per
   `CONTEXT_EVENT_EXTRACTION_GAZETTEER.md`'s validation checklist.
5. The 10-K/10-Q locator -- already the top-priority item on record since
   before this session started.
