# CONTEXT ADDENDUM — AIG Test Pass

**Date:** 2026-09-16

Part of the EDGAR M&A historical context. Keep alongside
`CONTEXT_EVENT_EXTRACTION.md`, `CONTEXT_EVENT_EXTRACTION_HARDENING.md`,
`CONTEXT_EVENT_EXTRACTION_SIX_FLAGS.md`,
`CONTEXT_EVENT_EXTRACTION_PARAMOUNT.md`,
`CONTEXT_EVENT_EXTRACTION_BRINKER.md`, `CONTEXT_EVENT_EXTRACTION_FORD.md`,
`CONTEXT_EVENT_EXTRACTION_TESLA.md`, and
`CONTEXT_EVENT_EXTRACTION_GAZETTEER.md`.

## Why this pass happened

Sixth untested company, and the first from the insurance industry.
Deliberately picked to be two things at once: a large, clean full
acquisition (Validus Holdings, 2018) to keep generalization-testing the
`AGREED_TO_ACQUIRE` pattern, and an entry point into looking at why every
`DIVESTED_BUSINESS` gold event tested so far (Lumen's 3, Disney's 1) has
come back `NOT_DISCOVERED` -- AIG has a real, well-documented divestiture
(Validus Re to RenaissanceRe, 2023) that could have been a next target.
Found two more real bugs on the acquisition side before getting to the
divestiture side at all.

## Bug 8 — FIXED: an adjective between "a[n]" and the agreement name broke the trigger entirely

Real AIG/Validus text: "entered into **a definitive** agreement and plan
of merger" -- the trigger regex expected the agreement name immediately
after "a[n]", with nothing in between. Confirmed directly: zero events at
all before the fix, on an otherwise completely ordinary, single-acquirer
merger announcement.

**Fix:** added a curated adjective list (`definitive|binding|new`) that
can optionally sit between the article and the agreement name, in both
the trigger regex and its `financing`-guard companion. Deliberately kept
curated rather than a generic wildcard -- the Tesla pass already showed
what a permissive capture group can do (swallow leading preamble text).
Full suite: 225/225 immediately after.

## Bug 9 — FIXED: shell named first in a "with X and Y" clause was picked as target

Even with bug 8 fixed, the same real text still produced the WRONG
target: `AGREED_TO_ACQUIRE American International Group, Inc. -> Venus
Holdings Limited` (the merger-sub shell) instead of `Validus Holdings,
Ltd.` (the real company). Root cause: unlike Six Flags/Paramount, where
all parties were listed in the PREAMBLE before "entered into", this text
names the real acquirer up front, then lists the shell and the real
target together in a `with X and Y` clause AFTER the trigger phrase --
"...entered into [agreement] with Venus Holdings Limited, a wholly owned
subsidiary of AIG ('Merger Sub') **and** Validus Holdings, Ltd.
('Validus')...". The existing shell-exclusion logic (built for Six Flags)
only applied to the preamble; the `with X` clause's target resolution
still used a bare `known_prefix()` prefix match, which grabbed whichever
org came first regardless of shell status.

**Fix:** extracted the preamble's shell-exclusion logic into a shared
`_non_shell_orgs_in()` helper and applied it to the `with X` clause too,
not just the preamble.

**A second, distinct bug turned up while fixing this one:** the first
attempt still failed, because the `with X` clause was being captured with
a `[^.;]{2,180}` pattern that stops at the first period -- and "Validus
Holdings, Ltd." itself ends in a period ("Ltd."). The capture cut off
mid-suffix, so the literal org string "Validus Holdings, Ltd." (with its
own trailing period) never appeared as a substring of the captured text
at all. This is a real, structural risk in any regex that uses a period
as a stop character near text containing suffix abbreviations that
themselves end in periods (Ltd., Inc., Corp., Co.) -- worth keeping in
mind if similar period-bounded captures get added elsewhere.

**Fix for that:** stopped truncating the span at the first period before
handing it to the shell-exclusion check -- feed it a wider raw window
instead (300 chars after "with"), since `_non_shell_orgs_in()` already
does its own scoping via the shell-context check between each org's own
mention and the next, and doesn't need a clean sentence-bounded string
the way the old exact-prefix match did. The old truncated-capture path is
kept as a fallback only when no known org is found in the wider window at
all. Full suite: 225/225 after both fixes; two new regression tests added
(`test_agreed_to_acquire_allows_definitive_modifier`,
`test_agreed_to_acquire_skips_shell_named_first_in_with_clause`) --
227/227 total.

## Result, verified against the real Item 1.01 text

```
AGREED_TO_ACQUIRE  American International Group, Inc. -> Validus Holdings, Ltd.  COMPLETED
MERGED_INTO        Venus Holdings Limited -> Validus Holdings, Ltd.              PROPOSED
SUBSIDIARY_OF      Validus Holdings, Ltd. -> American International Group, Inc. PROPOSED
```

## Structural coverage gap (fourth real company, same shape as before)

The Validus closing 8-K (July 2018) was also filed under **Item 8.01**
("Other Events") -- a fourth real company (after Six Flags' Item 5.02,
Brinker's Item 8.01, Ford's Item 7.01) hitting a variant of the
item-filter gap. Diagnostic-only test of that text (bypassing the filter)
found entities resolve correctly but zero events fire: "issued a press
release announcing the completion of its acquisition of all outstanding
common shares of X" is yet another `ACQUIRED`-pattern phrasing variant
the extractor doesn't recognize -- not worth fixing in isolation for text
the live filter would never reach anyway.

Four real companies now hitting this same class of gap, each via a
different item code (5.02, 8.01 twice, 7.01) -- this is not an edge case
at this point, it's a genuine pattern. Revisiting the item filter is
looking like it should move up in priority.

## Divestiture side: not reached this pass

The Validus Re / RenaissanceRe divestiture (2023) was researched (see
gold file's note) but its 8-K text was never fetched, so a `DIVESTED_
BUSINESS` gold event for it wasn't added -- would have been an unfounded
record without verification. The "why do all divestitures fail" question
is still open; worth a dedicated look, either by fetching this AIG
divestiture's real text or by re-examining Lumen's/Disney's raw fixtures
against the `DIVESTED_BUSINESS` pattern specifically.

## New gold + raw fixtures

`data/eval_gold/aig.json` -- 2 events, scoped to the Validus Holdings
acquisition only (announced 2018-01-22, closed 2018-07-18). Gold
blindness PARTIAL -- an M&A aggregator and a real 8-K exhibit (2010
IPO-history background, unrelated to Validus) appeared in the same
search; the real Validus 8-K text was fetched afterward, for diagnostic
testing, not to write gold.

`data/eval_raw/aig_real.json` -- only the Item 1.01 announcement, for the
same reason as Six Flags/Ford/Brinker: the closing text isn't reachable
under the live item filter.

## Current aggregate (7 companies with raw data; Brinker/Ford still skipped)

7/24 (29.2%), 95% CI [0.15, 0.49].

## How to resume

```bash
python3 -m pytest tests/                          # confirm 227/227
cd code/eval && python3 run_coverage_eval.py --gold lumen.json disney.json tenable.json six_flags.json paramount.json brinker.json ford.json tesla.json aig.json
```

Next candidate work:
1. The item-filter revisit -- four real companies now, not an edge case.
2. Dig into why every `DIVESTED_BUSINESS` gold event has failed so far --
   either fetch AIG's Validus Re divestiture text, or re-diagnose Lumen's
   3 and Disney's 1 against the divestiture pattern specifically.
3. The registrant-self-reference generalization flagged in the Tesla pass
   -- still the single highest-leverage open item.
4. Continue the untested-company list: Netflix (last one).
