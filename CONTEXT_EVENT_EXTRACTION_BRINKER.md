# CONTEXT ADDENDUM — Brinker / Chili's Test Pass

**Date:** 2026-09-15

Part of the EDGAR M&A historical context. Keep alongside
`CONTEXT_EVENT_EXTRACTION.md`, `CONTEXT_EVENT_EXTRACTION_HARDENING.md`,
`CONTEXT_EVENT_EXTRACTION_SIX_FLAGS.md`,
`CONTEXT_EVENT_EXTRACTION_PARAMOUNT.md`, and
`CONTEXT_EVENT_EXTRACTION_GAZETTEER.md`.

## Why this pass happened

Third untested company from the original list, deliberately different in
kind from Six Flags/Paramount rather than another headline media merger:
Brinker does small, recurring franchisee-restaurant buybacks, not
whole-company mergers. Picked specifically to test a structurally
different deal shape.

## Finding — not a parsing bug, a structural coverage gap (unfixed, quantified)

Brinker's real acquisition history is essentially invisible to the current
pipeline **for reasons that have nothing to do with entity/event
extraction quality**, confirmed two separate ways:

1. **Most of it lives only in 10-Q footnotes, never a standalone 8-K.**
   The 2021-2022 Mid-Atlantic/Great Lakes/Northwest Region acquisitions
   are disclosed exclusively in 10-Q Note 2/Note 15 ("CHILI'S RESTAURANT
   ACQUISITIONS") -- no 8-K exists for any of them (real, checked, not
   assumed). This is exactly the "no 10-K/10-Q fetcher exists at all" gap
   already on record as the single biggest open item in
   `CONTEXT_EVENT_EXTRACTION.md` -- Brinker is the first company tested
   where that gap accounts for the *entire* miss, not a partial one.
2. **The one deal that did get a dedicated, standalone 8-K used Item
   8.01 ("Other Events")** -- not 1.01 or 2.01. Confirmed directly: the
   2015 Pepper Dining Holding Corp. acquisition ($106.5M, 103 restaurants)
   got its own 8-K, entirely about the acquisition, filed under Item 8.01.
   `fetch_8k_ma_filings()`'s item filter (`"1.01" in items or "2.01" in
   items`) excludes it completely.

This is a meaningfully different variant of the item-filter problem than
Six Flags' finding: Six Flags' closing confirmation was a needle bundled
into an unrelated Item 5.02 filing (about executive comp) -- a needle-in-
haystack problem. Brinker's 8-K is *entirely* about the acquisition; the
whole haystack is the needle, just filed under a catch-all item code the
filter doesn't scan at all. Two real companies now, two different reasons
the same filter gap bites -- reinforces that revisiting the item filter
(already queued) is worth doing as its own real piece of work, not a
one-off special case.

**Diagnostic only (not reachable, so not worth fixing in isolation):**
even parsing the Item 8.01 text directly (bypassing the filter for
diagnosis) finds zero events -- the phrasing is "announced it has acquired
Pepper Dining Holding Corp.", which matches neither the `AGREED_TO_ACQUIRE`
trigger nor the existing `ACQUIRED` pattern ("completed ... acquisition of
X" / "the previously announced transaction with X"). Entity extraction
itself is fine here (`Brinker International, Inc.` and `Pepper Dining
Holding Corp.` both resolve correctly, no suffix issues). Not fixing this
phrasing gap now: it's moot without also revisiting the item filter, and
patching phrasing for text the live system can't even reach yet would be
solving the wrong problem first.

## New gold file, no raw fixture (deliberately)

`data/eval_gold/brinker.json` -- 2 events, scoped to only the two Brinker
acquisitions that both named a real counterparty organization AND got a
dedicated 8-K (Pepper Dining Holding Corp. 2015, ERJ Dining 2019). The
2021-2022 region acquisitions are real but excluded from gold even though
they're documented -- they never name a counterparty organization at all
("previously franchised restaurants located in the Mid-Atlantic region"),
so there's no organization for the system to ever recall regardless of any
fix. Gold blindness PARTIAL -- 10-Q footnote text appeared in the same
search as the independent news sources.

No `data/eval_raw/brinker*.json` was created. Nothing is legitimately
reachable via the current live pipeline (no 10-Q fetcher, item filter
excludes 8.01), so per the same discipline established in the Six Flags
pass, fabricating a fixture with unreachable text would inflate the
coverage score artificially. Confirmed the harness's own behavior here is
already correct and honest:

```
$ python3 run_coverage_eval.py --gold brinker.json
[Brinker International, Inc.] no raw filing data found in data/eval_raw/brinker*.json -- skipping
```

Brinker is excluded from the aggregate entirely (`companies_evaluated: 5`,
unchanged) rather than silently scored 0/2 -- the harness's existing
"skip, don't fake a score" behavior is exactly right for this case and
needed no changes.

## How to resume

```bash
python3 -m pytest tests/                          # confirm 221/221
cd code/eval && python3 run_coverage_eval.py --gold lumen.json disney.json tenable.json six_flags.json paramount.json brinker.json
```

Brinker's gold file sits waiting for a raw fixture once either of the two
structural gaps above gets addressed:
1. A 10-Q fetcher/locator (already the top-priority item on record) would
   make `brinker-1`/`brinker-2` reachable via 10-Q footnote text even
   without touching the 8-K item filter at all.
2. Widening the 8-K item filter to include 8.01 (or some form of scanning
   catch-all "Other Events" filings for merger-adjacent language) would
   make the actual 2015 8-K reachable, but would then also need the
   "announced it has acquired X" phrasing gap fixed to do anything useful
   with it.

Continue the untested-company list: Ford, Tesla, AIG, Netflix.
