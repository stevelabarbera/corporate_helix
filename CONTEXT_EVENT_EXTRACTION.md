# CONTEXT — EDGAR M&A Discovery & Coverage Evaluation Thread

Paste this into a FRESH conversation to resume. Don't continue growing one
giant thread — token cost compounds with conversation length, this doc
exists specifically to avoid that. This file supersedes the older version
of itself referencing `fetch_edgar_events.py`/`generate_event_report.py` —
those were an earlier generation, superseded by everything below.

## What this thread is

Two things, built together because the second depends on the first:

1. **Recursive M&A discovery**: given a company, find every merger/
   acquisition it's been part of via SEC EDGAR, then recurse into every
   other company that surfaces, until nothing new turns up. Falls back to
   GLEIF's relationship data when EDGAR goes quiet on a company (most
   commonly: it stopped filing independently after being absorbed).
2. **Coverage evaluation harness**: a scientific, stage-tagged way to
   measure how much real M&A activity this actually catches, using gold
   data written from independent sources *before* looking at any filing
   text, scored with real confidence intervals.

Part of Corporation Helix (subsidiary/related-entity resolution for ASM) —
full project context lives in your own CORPORATION_HELIX_CONTEXT doc; this
file only covers the EDGAR sub-thread.

## Current architecture (this session's real, current files)

- `code/providers/edgar_resolver.py` — general SEC company name → CIK
  resolution via `company_tickers.json` (replaces the old hardcoded
  three-company dict), plus 8-K fetch/section-splitting
- `code/providers/edgar_ma_provider.py` — `EdgarMAExpansionProvider`,
  plugs into the same `iterative_expansion.run_expansion()` engine used
  for GLEIF expansion. `other_party()` decides which side of an event is
  the newly-discovered company
- `code/providers/gleif_identity_fallback_provider.py` — picks up when
  EDGAR has nothing left to say about a company
- `code/run_company_ma_expansion.py` — CLI: `python3 code/run_company_ma_expansion.py --company "X"`
- `code/benchmark_m385_merger_coref.py` — the actual entity/event
  extraction engine (`RegexBackend`, `SpacyBackend`, `LegalRulesBackend`,
  `fuse()`, `infer_events()`). This is what does the real work; the
  provider above just wires it into the recursive-discovery loop
- `code/eval/coverage_harness.py` + `code/eval/run_coverage_eval.py` —
  the evaluation harness. Gold files live in `data/eval_gold/*.json`
  (each documents whether/how blindly it was established), real fetched
  filing text in `data/eval_raw/*.json`

Run `python3 -m pytest tests/` before doing anything else — 203 tests,
all passing as of this session, including everything below.

## Real bugs found and fixed this session (all confirmed against real fetched SEC text, not hypothetical)

1. **Entity-name regex swallowed whole clauses.** Unbounded character class
   between an initial capital letter and a corporate suffix let it match
   an entire sentence back to the nearest earlier capitalized word (real
   example: "Disney will make a cash payment to New Fox, Inc." extracted
   as one org name instead of "New Fox, Inc."). Fixed with a word-chain
   constraint (each word capitalized/digit-led or a small connector
   whitelist, capped at 8 words).
2. **Hardcoded company-name whitelists** (`for a in ("Company","Broadcom","Cisco")` / `("Splunk","VMware")`) in the acquirer/target-detection
   fallbacks — literally the two benchmark companies, by name. This is
   the concrete reason the parser "worked" on Broadcom/Cisco and fell
   apart on everything else. Replaced with general mechanisms; kept only
   the genuinely universal "the Company" self-reference convention.
3. **`known_prefix()` truncation bug** — the calling regex's capture stops
   at the first `.`/`;`, which routinely lands inside an org's own legal
   suffix. Compounded bug #2 by silently covering for it on the two
   benchmark companies without anyone noticing it was broken generally.
4. **No "Company" corporate suffix.** Any company whose legal name ends
   in the plain word "Company" (not Inc./Corp./LLC) — The Walt Disney
   Company, Ford Motor Company, The Boeing Company, The Coca-Cola
   Company — was entirely invisible to entity extraction. Found via a
   real Disney 8-K. Fixed with an exact-match guard against the generic
   "the Company"/"the Corporation" self-reference so it doesn't become a
   new false-positive source.
5. **`EdgarMAExpansionProvider` used an unvalidated 2-backend ensemble**
   (regex + legal_rules, threshold 1.0) instead of the actual validated
   3-backend one from the benchmark's own `main()` (regex + spaCy +
   legal_rules, threshold 1.5). Meant any org mentioned without a nearby
   alias-defining parenthetical was silently dropped. Fixed to match the
   validated configuration exactly.
6. **Closing-detection regex missed real phrasing.** Only matched
   "completed its acquisition of X" / "completed the previously
   announced transaction with X" — real text from BOTH Lumen and Tenable
   independently uses "completed its previously announced acquisition
   (the "Acquisition") of X", which matched neither. Confirmed on two
   unrelated companies before generalizing (not a guess). Directly moved
   measured recall from 0/11 to 3/11 on those two companies alone.
7. **Evaluation harness only tried a company's CURRENT name**, so a
   filing from before a rebrand/restructuring (Lumen was CenturyLink
   until 2020; Disney's holdco literally swapped names with its own
   former self at closing) scored zero even after bug #6 was fixed —
   masking real progress. Fixed by wiring up the `aliases_ok` list
   already sitting unused in every gold file.

## New capability added: 10-K declarative-acquisition pattern

Confirmed via direct testing that **no 10-K support existed at all**
before this session — `infer_events()` only understood 8-K-style
third-person contract language. A 10-K's Business Combinations footnote
is written in first person about the filer itself ("In October 2023, we
acquired Ermetic Ltd. ... We acquired 100% of Ermetic's equity...").
Added a new pattern for "we acquired [100% of] X['s equity]", with a
`REGISTRANT_SELF_REFERENCE` sentinel (the acquirer is always the filer,
never named) that `other_party()` resolves to whichever pivot is being
queried. Verified end-to-end on real Tenable 10-K text: correctly
discovers both Ermetic and Bit Discovery.

**This proves the extraction works once given 10-K text. It does NOT
include a fetcher that goes and finds that text on its own** — see "The
biggest open gap" below.

## Real coverage-evaluation results (3 companies, real fetched SEC filings)

| Company | Gold events | Recalled | What was found |
|---|---|---|---|
| Lumen/CenturyLink | 5 | 2 | Level 3 agreement + closing both recalled (after fixes #6, #7). 3 divestitures (Brightspeed, Stonepeak, Colt) not tested — see divestiture gap below |
| Disney | 4 | 0 | Both Fox agreements + closing missed for a THIRD, still-open reason: regex and spaCy disagree about where "Twenty-First Century Fox Inc." starts (regex finds the full name, spaCy finds only "Fox Inc."). Since `fuse()` votes by exact string match, the two backends split their vote instead of combining it, and neither alone reaches threshold. Real architecture gap in the voting mechanism, not a quick patch |
| Tenable | 6 | 1 | Ermetic recalled after fix #6. Indegy/Alsid/Accurics/Cymptom/Bit Discovery not yet tested against real filing text — and Bit Discovery is CONFIRMED to have no standalone 8-K at all (only a mention inside a quarterly-earnings 8-K) |

**Aggregate: 3/15 (20%), 95% CI [0.07, 0.45].** Read the interval, not
just the point estimate — this is still a small sample.

**Alsid and Accurics were missing from the original Tenable gold list
entirely** — caught not by research but by the user (a former Bit
Discovery/Tenable employee) manually reading Tenable's real 10-K tax
footnote. This is the gold-labeling discipline working as intended: an
error got caught and corrected in the open rather than silently baked
into a score nobody double-checked.

## No divestiture pattern exists at all

Confirmed by code reading, not just by these results: `infer_events()`
has zero pattern for "sold," "divested," "completed the sale of," etc.
Lumen's 3 missing events are all divestitures — this alone likely
accounts for most of Lumen's remaining gap.

## The biggest open gap: there is no 10-K (or 10-Q, or anything else) fetcher

Confirmed jointly by the user's own manual EDGAR/10-K review: **there is
no single canonical section to target.** Acquisitions in one real 10-K
showed up in three different places: a clean "Business Combinations"
table, oblique tax-expense bullet points naming acquisitions only as
possessive references ("...related to the Bit Discovery acquisition"),
and financial charts. A locator needs to scan the whole document for
acquisition-related anchor words and extract surrounding context, not
assume one section name. The extraction logic itself (once given the
right text) already works — this is purely a "where do I look" problem,
which is what makes it tractable rather than another open-ended research
problem like alias resolution.

## EDGAR document-type expansion roadmap (discussed, not yet built — prioritized)

1. **10-Q** (next, cheapest win with the most reuse) — same
   "Business Combinations" footnote structure as a 10-K, filed quarterly
   instead of annually. Real payoff: catches acquisitions months before
   they'd show up in the annual 10-K. The 10-K locator/fetcher work
   above should mostly transfer directly.
2. **8-K Item 5.01** ("Changes in Control of Registrant") — a same-day,
   one-line filter addition to the existing 8-K fetcher (it currently
   only keeps 1.01/2.01). No new parsing needed.
3. **Proxy statements (DEFM14A) and S-4 registration statements** — for
   any deal needing a shareholder vote (most large stock-for-stock
   deals — Disney/Fox is the exact example). These contain a dedicated
   "Background of the Merger" narrative section and are often the
   single richest source that exists for a big contested deal. Real new
   parsing target, not a quick reuse — much longer documents, different
   structure, more narrative prose.
4. **Form 425** (ongoing deal communications/amendments) — likely
   parses with what already exists, 8-K-like structure. Value is
   catching updates to a known deal, not new discovery.
5. **SC 13D/13G (beneficial ownership) and tender offer materials
   (SC TO-T/14D9)** — a genuinely different category of activity
   (activist stake-building, unsolicited/hostile takeovers) that
   doesn't go through negotiated-merger language at all. Real coverage
   gap, but a separate project from "read acquisition footnotes
   better," not a quick extension of the current patterns.

## Other confirmed-but-not-fixed open items

- **Disney's cross-backend entity-boundary voting mismatch** (see table
  above) — needs either fuzzy/overlap-based vote merging instead of
  exact-string matching, or a canonicalization step before voting. A
  real architecture question, deliberately left rather than rushed.
- **Name-history architecture, generally** — the `aliases_ok` fix above
  solves it for the evaluation harness specifically, but the live
  `EdgarMAExpansionProvider` used for real recursive discovery still
  only tries a pivot's current/given name. Should probably tie into
  GLEIF's own historical-name data eventually.
- **`HelixFact` identity/enrichment gap** (flagged earlier, still open):
  when the GLEIF fallback resolves an LEI for a company EDGAR already
  discovered by name, it creates a second fact instead of enriching the
  existing one, since `None` vs. a real LEI are different dedup keys.
- **`code/resolution/resolver copy.py`** — still sitting in the repo,
  confirmed stale, still low-risk since nothing imports it. Never got
  around to deleting it.

## How to resume

```bash
python3 -m pytest tests/                          # confirm nothing broke
cd code/eval && python3 run_coverage_eval.py --gold lumen.json disney.json tenable.json
```
If both pass/run cleanly, you're safely picked back up. Then pick a
target: the 10-Q locator (highest value), the Disney voting-fusion fix,
or expanding the gold set to more of the original ten companies (Six
Flags, Chili's/Brinker, Paramount, Ford, Tesla, AIG, Netflix still
untested).
