# CONTEXT ADDENDUM — Ford Test Pass

**Date:** 2026-09-15

Part of the EDGAR M&A historical context. Keep alongside
`CONTEXT_EVENT_EXTRACTION.md`, `CONTEXT_EVENT_EXTRACTION_HARDENING.md`,
`CONTEXT_EVENT_EXTRACTION_SIX_FLAGS.md`,
`CONTEXT_EVENT_EXTRACTION_PARAMOUNT.md`,
`CONTEXT_EVENT_EXTRACTION_BRINKER.md`, and
`CONTEXT_EVENT_EXTRACTION_GAZETTEER.md`.

## Why this pass happened

Fourth untested company, deliberately picked (like Brinker) as a
low-M&A-frequency company to test the structural-gap case again, from a
different industry. Confirmed the same shape as Brinker, plus one new
real bug.

## Bug 6 — FIXED: entity name bled across a blank-line section-header boundary

Real Ford 10-K text (`ACQUISITIONS AND DIVESTITURES` header, on its own
line, followed by `Company Excluding Ford Credit` on the next line, then a
blank line, then `Electriphi, Inc. ("Electriphi"). On June 18, 2021, we
acquired Electriphi...`) was captured by `RegexBackend` alone as a single
entity spanning the entire header: `"ACQUISITIONS AND DIVESTITURES Company
Excluding Ford Credit Electriphi, Inc."` -- confirmed directly.

Root cause: the entity word-chain join separator was `[\s-]+`, and `\s`
treats a blank line (`\n\n`, a real paragraph/section break) identically
to a single space. The 8-word cap on the word-chain was not the
protection it looked like -- "ACQUISITIONS AND(connector) DIVESTITURES
Company Excluding Ford Credit Electriphi" is only 7 words, comfortably
under the cap, once newlines stopped mattering as boundaries at all.

**Fix:** introduced `_JOIN = r"(?:[ \t-]+|\n(?!\s*\n))"` -- a single
newline (ordinary line-wrapping within one sentence) still joins, but two
consecutive newlines (an actual paragraph/section break) now stops the
word-chain. Applied to both `ENT` and `ENT_LEGALFORM`'s word-chain
junctions (same bug class in both). Full suite stayed 213/213 immediately
after, and all subsequent tests (223 total, see below) pass.

**A residual noise artifact exists but doesn't matter in practice:**
`RegexBackend` alone, tested in isolation, still emits a second, shorter
false-positive fragment ("ACQUISITIONS AND DIVESTITURES Company" -- since
"Company" is itself a valid corporate suffix, joined across the header's
own *single* internal newline, which the fix correctly still allows).
Tested through the full fused `EdgarMAExtractor` pipeline, this fragment
never survives: spaCy's NER doesn't corroborate a section header as an
ORG, so the fragment falls below the fusion vote threshold and is
correctly dropped before event inference ever sees it. Verified directly:
`ex.parse_section(...)['fused']['orgs'] == ['Electriphi, Inc.']`, clean.
Two new regression tests added to `tests/test_edgar_entity_boundary_fix.py`
-- one confirms the fix through the real fused pipeline (what actually
matters), one confirms ordinary single-line-wrapped entity names still
join correctly (the fix isn't overly strict).

## Structural coverage gap (same shape as Brinker, not re-fixed here)

Ford's two recent real, named acquisitions (Electriphi 2021, Auto Motive
Power/AMP 2023) are both small, terms-undisclosed startup acqui-hires --
neither got a substantive standalone 8-K:

- **Electriphi** IS disclosed in real, clean, parseable prose -- but only
  in the 10-K's "Acquisitions and Divestitures" footnote, confirmed above
  to now parse correctly once fetched. It still needs the already-flagged,
  still-nonexistent 10-K fetcher to ever actually reach that text live.
  This is a positive result in a different sense than Six Flags/Paramount's
  fixes: it confirms the existing 10-K declarative-acquisition pattern
  (`REGISTRANT_DECLARATIVE_ACQUISITION`, built for/validated on Tenable)
  generalizes correctly to a new company's phrasing without needing any
  new pattern work -- once the text is fetched.
- **AMP** has no equivalent reachable disclosure at all found. The
  closest-dated 8-K (Nov 30, 2023) uses Item 7.01 (Regulation FD
  Disclosure), generically furnishing a press-release exhibit with no
  entity-naming text in the item body itself ("Ford Motor Company's news
  release dated November 30, 2023 is furnished as Exhibit 99...").

Third real company now (after Six Flags' Item 5.02 and Brinker's Item
8.01) hitting a variant of the item-filter/exhibit-fetching gap. Ford's
variant is again different: the item body isn't wrong-but-substantive
(Brinker) or a needle in an unrelated filing (Six Flags) -- it's
deliberately, correctly-per-SEC-rules terse, with the real content
incorporated by reference into an unfetched exhibit.

## New gold file, no raw fixture (deliberately, same discipline as Brinker)

`data/eval_gold/ford.json` -- 2 events (Electriphi, AMP), scoped to these
two only. Ford's much larger historical acquisitions (Volvo Car 1999, Land
Rover 2000) predate practical full-text EDGAR coverage, same cutoff
rationale as every other gold file. Gold blindness PARTIAL -- a 10-K XBRL
fact table appeared in the same search as the independent sources; the
Electriphi 10-K sentence was seen afterward, during diagnostic testing of
the fix, not used to write the gold record itself.

No `data/eval_raw/ford*.json` -- nothing is legitimately reachable via the
current live pipeline (no 10-K fetcher for Electriphi; no substantive item
body at all for AMP). Confirmed the harness correctly skips it rather than
faking a score, same as Brinker.

## How to resume

```bash
python3 -m pytest tests/                          # confirm 223/223
cd code/eval && python3 run_coverage_eval.py --gold lumen.json disney.json tenable.json six_flags.json paramount.json brinker.json ford.json
```

Both Ford and Brinker's gold files now sit waiting on the same missing
piece: a 10-K/10-Q fetcher. That's now the single highest-leverage item on
the whole backlog -- it's the one gap that would make BOTH companies'
gold events reachable, not just one.

Continue the untested-company list: Tesla, AIG, Netflix.
