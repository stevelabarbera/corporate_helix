# CONTEXT ADDENDUM — Six Flags / Cedar Fair Test Pass

**Date:** 2026-09-15

Part of the EDGAR M&A historical context. Keep alongside
`CONTEXT_EVENT_EXTRACTION.md` and `CONTEXT_EVENT_EXTRACTION_HARDENING.md`.

## Why this pass happened

Per the "How to resume" list in `CONTEXT_EVENT_EXTRACTION.md`, Six Flags was
one of the untested companies (Six Flags, Chili's/Brinker, Paramount, Ford,
Tesla, AIG, Netflix) earmarked for expanding the gold set — deliberately
picked to run real functionality against a new company and surface whatever
broke, rather than to add another clean win.

It surfaced two real, distinct bugs on the first real filing tested (both
fixed and verified this pass), plus one documented, deliberately-not-fixed
gap in the 8-K item filter itself (finding 3).

## Environment note (not a code bug)

Before any of this, a plain `pytest tests/` run in a fresh environment showed
33 failures. Root cause: missing `spacy`/`en_core_web_sm` and `tldextract`
packages, not code rot — `EdgarMAExtractor` and `registrable_domain()` both
correctly *refused* to silently substitute degraded behavior, per the
hardening pass. Installing both packages brought the suite to 213/213
passing, matching the documented checkpoint exactly.

## Bug 1 — FIXED: "L.P." was not a recognized corporate suffix

`CORP` (the regex alternation of corporate suffixes entity extraction relies
on) had `Inc./Incorporated/Corporation/Corp./LLC/L.L.C./Ltd./Limited/PLC/plc/
Company` — no limited-partnership suffix at all. Cedar Fair, L.P. (a real
counterparty, not a hypothetical) was therefore **completely invisible** to
all three backends; it never entered `orgs` or `aliases`, so nothing
downstream could ever reference it. This is the same shape as the earlier
"the Company"/"the Corporation" suffix gap (bug #4 in the original session),
just for a suffix nobody had tested yet, because none of Lumen/Disney/Tenable
involved a limited partnership.

**Fix:** added `L\.P\.|LP` to `CORP` in `code/parsers/edgar_ma_extractor.py`.
Low-risk, single-line, confirmed against real filing text, full suite still
213/213 after the change.

## Bug 2 — FIXED: merger-of-equals phrasing wasn't recognized

Even after fix #1, the real Item 1.01 announcement 8-K produced **zero**
events. Two independent pattern misses compounded:

1. **`AGREED_TO_ACQUIRE` target resolution assumed a single acquirer +
   "with Target" naming the target's full legal name.** The Six Flags/Cedar
   Fair 8-K instead pre-lists all four parties (Six Flags, Cedar Fair,
   HoldCo, Merger Sub) *before* "entered into an Agreement and Plan of
   Merger", then never says "with Target" at the top level. Worse: the
   naive "last org mentioned before the match" heuristic resolved `acq` to
   `CopperSteel Merger Sub, LLC` — a transitory shell formed solely to
   effect the merger — and since neither shell is ever the pivot company,
   `other_party()` silently dropped the event regardless of what `target`
   resolved to.
   **Fix:** before the match, collect the real (non-shell) parties in
   order of first mention, excluding any entity introduced as "a
   subsidiary of X" in its own descriptor clause (careful to scope each
   entity's context to only its own clause, not bleed into the next
   entity's descriptor in the same run-on sentence). Use the first real
   party as `acq`, and fall back to a second real party as `target` when
   the post-match text never repeats the target's full legal name (which
   it doesn't here — only the short alias "Cedar Fair" reappears).
2. **`MERGED_INTO`'s regex required the literal word "merged"** (`(will be|
   was)? merged with and into`), but this forward-looking announcement text
   uses present-tense "will merge with and into" — a verb form the pattern
   didn't recognize at all. **Fix:** the regex now accepts `(?:merge|
   merged)` with the same modal handling, so "will merge with and into" is
   recognized as PROPOSED alongside the existing "was merged"/"will be
   merged"/bare "merged" (COMPLETED) forms.

**Result, verified against the real Item 1.01 text:**
```
AGREED_TO_ACQUIRE  Six Flags Entertainment Corporation -> Cedar Fair, L.P.        COMPLETED
MERGED_INTO        CopperSteel Merger Sub, LLC          -> Cedar Fair, L.P.        PROPOSED
MERGED_INTO        Six Flags Entertainment Corporation  -> CopperSteel HoldCo, Inc. PROPOSED
```
The first line is a genuine recall hit against `six_flags-1`
(AGREED_TO_ACQUIRE/COMPLETED). Full suite stayed 213/213 after both fixes.
Six Flags moved from 0/2 to 1/2; aggregate across 4 companies moved from
3/17 (17.6%) to 4/17 (23.5%, CI [0.10, 0.47]).

`six_flags-2` (the closing/MERGED_INTO event) still shows NOT_DISCOVERED —
correctly, since no closing-8-K text is in the fixture at all (see finding
3 below), not because of a remaining pattern gap.

## Finding 3 — documented gap, no fix attempted: this deal's closing text isn't reachable at all

The closing confirmation for this merger was **not** filed as a standalone
Item 2.01 8-K. It's bundled into an Item 5.02 filing (CIK 1999001, accession
0001193125-24-176370, filed 2024-07-08, primarily about Selim Bassoul's
employment agreement). `fetch_8k_ma_filings()`'s item filter (`"1.01" in
items or "2.01" in items`) would never retrieve this filing in live
operation — so even after bugs #1/#2 above are fixed, this specific deal's
*closing* event would remain undiscoverable without also loosening or
rethinking that item filter. Deliberately **not** included in
`data/eval_raw/six_flags_real.json` for this reason — see that file's own
`note` field. This is a new variant of the "no single canonical section"
problem already on record for 10-Ks, now shown to also apply to 8-Ks.

## New gold file

`data/eval_gold/six_flags.json` — 2 events (announcement, closing), scoped to
the 2023-2024 Cedar Fair merger only (Six Flags' full ownership history —
Bally 1982, Wesray 1987, Premier Parks 1998 rename — predates EDGAR's
practical full-text coverage and was out of scope). Gold blindness is
**PARTIAL**, not full: general web search for the company's M&A history
surfaced some 10-K/10-Q search-result snippets alongside independent
sources before the gold file was written. No 8-K text was seen beforehand.
See the file's own `blindness_caveat` for the exact scope of that exposure.

Also newly on record for the *first* time: a merger where the pre-merger and
post-merger entities share the **identical** legal name ("Six Flags
Entertainment Corporation") across two different CIKs (701374 vs. 1999001,
the latter EDGAR-labeled "/NEW"). Unlike Lumen/CenturyLink or Disney's
holdco swap, this can't be told apart by alias string matching alone —
worth keeping in mind whenever the CIK-history / name-history architecture
gap already on record gets addressed.

## Current aggregate (4 companies)

4/17 (23.5%), 95% CI [0.10, 0.47] — up from 3/17 after bugs #1 and #2. Six
Flags itself is 1/2; the remaining miss (the closing event) is root-caused
to finding #3 below, not an unexplained gap.

## How to resume

```bash
python3 -m pytest tests/                          # confirm 213/213
cd code/eval && python3 run_coverage_eval.py --gold lumen.json disney.json tenable.json six_flags.json
```

Next candidate work, in rough priority order:
1. Revisit the 8-K item filter (currently 1.01/2.01 only) in light of
   finding #3 — at minimum, decide whether 5.02 needs scanning for merger-
   closing language the way 2.01 is scanned, or whether this is better
   solved by the already-planned 8-K Item 5.01 expansion work. This is the
   only thing standing between the current code and recalling
   `six_flags-2`.
2. Everything already queued in `CONTEXT_EVENT_EXTRACTION.md`: 10-Q locator,
   Disney's cross-backend voting fix, remaining untested companies
   (Chili's/Brinker, Paramount, Ford, Tesla, AIG, Netflix).
