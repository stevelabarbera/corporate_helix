# CONTEXT ADDENDUM — Paramount / Skydance Test Pass

**Date:** 2026-09-15

Part of the EDGAR M&A historical context. Keep alongside
`CONTEXT_EVENT_EXTRACTION.md`, `CONTEXT_EVENT_EXTRACTION_HARDENING.md`, and
`CONTEXT_EVENT_EXTRACTION_SIX_FLAGS.md`.

## Why this pass happened

Second untested company from the original list, picked deliberately as
another recent (2024-2025) multi-party media-industry deal, to see whether
the Six Flags fixes generalized or whether a different real deal would
surface something new entirely. It's the latter — this is by a wide margin
the most structurally complex filing tested to date: five entities (four of
them merger-vehicle shells), a two-step transaction (an investor group
first buys the controlling parent, then a separate merger combines the
operating companies), and a registrant name with no corporate suffix at
all.

## Bug 4 — FIXED: suffix-less registrant names were completely invisible

`Paramount Global` -- the actual pivot company -- never appeared in `orgs`
at all, because `ENT` requires a name to end in a recognized corporate
suffix (Inc./Corp./LLC/Company/etc.), and "Global" isn't one. Confirmed
directly: `ENT` produces zero matches against `"Paramount Global, a
Delaware corporation (\"Paramount\" or the \"Company\")"`. spaCy's own NER
*did* independently flag "Paramount Global" as an ORG, but at weight 1.0
alone it falls below the fusion threshold (1.5) without corroboration from
another backend — so it was silently dropped during fusion, not missing
from spaCy's own output.

**Fix:** added a second, generic entity pattern (`ENT_LEGALFORM`) that
recognizes the "X, a/an `<State>` corporation/company/limited liability
company/limited partnership" construction directly — a signal every one of
these real filings already uses regardless of whether X itself has a
recognizable suffix. Wired into both `RegexBackend` and `LegalRulesBackend`
so their votes now corroborate spaCy's, pushing "Paramount Global" over the
fusion threshold. Filtered out a class of false positives this introduces:
`ENT_LEGALFORM` also naively matches the bare suffix token immediately
preceding a *different* entity's own legal-form clause (e.g. "Cedar Fair,
L.P., a Delaware limited partnership" would otherwise also match "L.P."
alone as a fake second entity) — `_BARE_SUFFIX` excludes any match that is
itself nothing but a known suffix. Full suite stayed 213/213; re-ran
against the Six Flags/Lumen/Disney/Tenable fixtures too, no score changes
anywhere.

This is a more consequential fix than any single-suffix gap (bug #1's L.P.
fix): it's not one more suffix to add to a list, it's an entirely
suffix-independent signal, so it should generalize to registrant names not
yet seen (e.g. "Alphabet", "Meta Platforms" -- worth keeping an eye on as
more companies get tested).

## Bug 5 — FIXED: the trigger phrase was hardcoded to one exact agreement name

Even with `Paramount Global` now visible, the whole `AGREED_TO_ACQUIRE`
block never fired at all, because it only triggers on the literal phrase
"entered into a[n] Agreement and Plan of Merger" -- and this filing instead
says "entered into a **Transaction Agreement**". Real, different companies
genuinely use different definitive-agreement names for economically
equivalent transactions.

**Fix:** both the trigger regex and the financing-guard check (`merger_exec`)
now accept a small, curated set of common M&A agreement names: "Agreement
and Plan of Merger", "Transaction Agreement", "Business Combination
Agreement", "Agreement and Plan of Reorganization". Deliberately did not
try to make this fully generic (e.g. matching any capitalized "* Agreement"
phrase) -- that would risk false-triggering on financing agreements, voting
agreements, etc., which the existing `financing` guard is specifically
there to filter out. Full suite stayed 213/213 after this change too.

## Result, verified against the real Item 1.01 text

```
AGREED_TO_ACQUIRE  Paramount Global -> Skydance Media, LLC        COMPLETED
MERGED_INTO        Pluto Merger Sub II, Inc. -> New Pluto Global, Inc.  PROPOSED
MERGED_INTO        Sparrow Merger Sub, LLC -> Skydance Media, LLC PROPOSED
```

The first line is a genuine recall hit against `paramount-1`
(AGREED_TO_ACQUIRE/COMPLETED). Paramount scores 1/3 on this fixture;
aggregate across all 5 companies now 5/20 (25%, CI [0.11, 0.47]).

## New gold file

`data/eval_gold/paramount.json` -- 3 events, scoped to the 2024-2025
Skydance transaction only (announced 2024-07-07, closed 2025-08-07).
Paramount's much longer corporate lineage (Gulf+Western 1966, Viacom/CBS's
repeated 1999-2000 and 2019 mergers) is out of scope, same rationale as
Six Flags' pre-2023 ownership history. Gold blindness is PARTIAL --
Britannica Money encyclopedia entries (independent secondary sources, not
filing text) came up in the same search as the deal-history query.

`data/eval_raw/paramount_real.json` only contains the Item 1.01
announcement text. The 2025-08-07 closing and the separate NAI Transaction
closing were not fetched this pass (a scope choice, not a documented gap
the way Six Flags' Item 5.02 finding was) -- `paramount-2` and `paramount-3`
are expected `NOT_DISCOVERED` against this fixture for that reason.

## How to resume

```bash
python3 -m pytest tests/                          # confirm 213/213
cd code/eval && python3 run_coverage_eval.py --gold lumen.json disney.json tenable.json six_flags.json paramount.json
```

Next candidate work:
1. Fetch the Paramount closing 8-K (Aug 2025) and the NAI Transaction
   closing to actually test `paramount-2`/`paramount-3` recall, rather than
   leaving them as an intentionally-out-of-scope gap.
2. Continue the untested-company list: Chili's/Brinker, Ford, Tesla, AIG,
   Netflix (Paramount and Six Flags are now done).
3. Everything already queued: 10-Q locator, Disney's cross-backend voting
   fix, the Six Flags Item 5.02 item-filter gap.
