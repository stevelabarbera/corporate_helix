# CONTEXT ADDENDUM — AT&T Test Pass: DIVESTED_BUSINESS Was Never Implemented

**Date:** 2026-09-16

Part of the EDGAR M&A historical context. Keep alongside
`CONTEXT_EVENT_EXTRACTION.md`, `CONTEXT_EVENT_EXTRACTION_HARDENING.md`,
`CONTEXT_EVENT_EXTRACTION_SIX_FLAGS.md`,
`CONTEXT_EVENT_EXTRACTION_PARAMOUNT.md`,
`CONTEXT_EVENT_EXTRACTION_BRINKER.md`, `CONTEXT_EVENT_EXTRACTION_FORD.md`,
`CONTEXT_EVENT_EXTRACTION_TESLA.md`, `CONTEXT_EVENT_EXTRACTION_AIG.md`,
`CONTEXT_EVENT_EXTRACTION_NETFLIX.md`, and
`CONTEXT_EVENT_EXTRACTION_GAZETTEER.md`.

## Why this pass happened

Eighth company, added at the user's suggestion after the original seven-
company list was finished, specifically because AT&T's WarnerMedia
history was known to be structurally complex. It turned into something
bigger: a real divestiture from AT&T's side, chosen deliberately to
finally investigate the open question (flagged since the AIG pass) of
why every `DIVESTED_BUSINESS` gold event tested so far -- Lumen's 3,
Disney's 1 -- had come back `NOT_DISCOVERED`.

## The actual answer: DIVESTED_BUSINESS had never been implemented at all

Checked directly: `grep -n "DIVESTED_BUSINESS" code/parsers/edgar_ma_extractor.py`
returned **zero matches**, before this pass. Only `AGREED_TO_ACQUIRE`,
`ACQUIRED`, `MERGED_INTO`, `SUBSIDIARY_OF`, and `CONVERTED_TO` had ever
been implemented. Every `DIVESTED_BUSINESS` gold event across every
company tested -- Lumen's 3, Disney's 1 -- was therefore guaranteed to
score `NOT_DISCOVERED` regardless of parsing quality, phrasing, or
anything else. This is a fundamentally different kind of finding than
every other gap found this session: not a regex refinement, a missing
*feature*.

Worth noting for the record: Lumen's own raw fixture doesn't even contain
divestiture-related text at all (checked directly -- its two filings are
the Level 3 announcement and closing only, from 2016-2017, years before
the 2021-2022 Brightspeed/Stonepeak/Colt divestitures). So Lumen's three
misses were doubly guaranteed: no matching text in the fixture, and no
pattern to find it even if there were. Disney's fixture DOES contain real
divestiture text (the Sinclair/FSN sale, in its own Item 2.01 section) --
this is what made building and validating a real fix possible this pass.

## Feature built: DIVESTED_BUSINESS pattern, validated against real Disney text

New pattern recognizing the shape: "`[Seller]` agreed to sell
`[Seller's]` interests in `[Business]` to `[Buyer]`" ... "the `[X]` Sale
was completed" -- built and validated directly against Disney's real,
already-on-disk fixture text (no new research needed for validation,
since that text was already sitting in `disney_real.json`):

```
"...Disney and FCN agreed to sell FCN's interests in Fox Sports Net, LLC
('FSN') to Buyer for a purchase price equal to $9.6 billion in cash...
(the 'FSN Sale')... the FSN Sale was completed."
```

Two real bugs found and fixed while building this, both the same bug
class already seen twice this session (AIG's `Ltd.` truncation):

1. **Buyer capture truncated at a decimal point.** The purchase price
   "$9.6 billion" has its own period; a `[^.;]`-bounded capture read it
   as the end of the buyer's name, producing `dm.group(1) == "Buyer for a
   purchase price equal to $9"`. Fixed by capturing a fixed-length window
   after "to " instead, and letting `known_prefix()`/`resolve()` find the
   real name within it -- they don't need a clean boundary the way an
   exact-prefix match did.
2. **The new `_parent_of()` helper had the same truncation bug on the
   parent-name side.** The real buyer, "Diamond Sports Group, LLC", is
   disclosed as "a wholly owned subsidiary of Sinclair Broadcast Group,
   **Inc.**" -- and "Sinclair Broadcast Group, Inc." itself contains a
   comma before its suffix, which the `[^.,;()]`-bounded capture excluded,
   cutting off before the suffix ("Sinclair Broadcast Group" without
   ", Inc."). Same fix: a fixed-length window instead of a punctuation-
   bounded capture.

**New helper: `_parent_of(org, text, orgs)`.** A divestiture's immediate
contracting buyer is very often a newly-formed shell subsidiary of the
real acquiring company -- exactly like Disney's real text. When an org is
disclosed as "a wholly owned subsidiary of X" in its own descriptor
clause, this resolves to the parent X instead. This is the *opposite*
direction from the existing `_non_shell_orgs_in()` helper (which
*excludes* shells entirely, for merger preambles where the shell is
irrelevant); here the shell *is* the contracting party, but the identity
that matters downstream is its parent.

**Verified end-to-end through the full eval harness, not just the
pattern in isolation:**

```
DIVESTED_BUSINESS  The Walt Disney Company -> Sinclair Broadcast Group, Inc.  COMPLETED
```

Exact match to Disney's existing gold record (`disney-4`). Disney moved
0/4 -> 1/4; aggregate across companies with raw data moved 8/25 (32%) ->
9/25 (36%). Full suite: 229/229 (227 baseline + 2 new tests). No changes
to any other company's score.

## AT&T's own divestiture: a different, harder shape -- confirmed, not fixed

AT&T's WarnerMedia separation is a **Reverse Morris Trust** transaction:
AT&T transfers WarnerMedia into a new subsidiary ("Spinco"/Magallanes,
Inc.), distributes Spinco's shares to AT&T's own stockholders, and
*then* merges that spun-off entity into Discovery. Confirmed directly
that the new `DIVESTED_BUSINESS` pattern does not fire on this text, as
expected -- "the Company will transfer the business...to Spinco" /
"the Company will distribute to its stockholders the shares..." is a
fundamentally different construction from "agreed to sell...to Buyer",
not a phrasing variant of the same shape. Deliberately not forcing a
broader pattern to cover both shapes under time pressure -- the Tesla and
AIG passes already showed what an overly permissive capture can do, and
a spin-off-then-merge structure is different enough in kind (three
sequential steps, an intervening internal reorganization, no single
"agreed to sell to X" sentence at all) that it deserves its own dedicated
design and validation pass rather than a rushed extension.

**A second, separate gap on the same AT&T text**: even the
`AGREED_TO_ACQUIRE` trigger doesn't fire. The real phrasing is "entered
into **certain definitive agreements** ... including (1) an Agreement
and Plan of Merger ... and (2) a Separation and Distribution Agreement"
-- the agreement name is introduced as item (1) of a list, not
immediately after "entered into a[n]" the way every other trigger-phrase
fix this session handled (a single adjective for AIG, an alternate
agreement name for Paramount). This is a larger structural difference
than either of those, not a small extension of the existing curated
list -- confirmed, documented, not fixed this pass.

## New gold + raw fixtures

`data/eval_gold/att.json` -- 1 event (the WarnerMedia/Discovery
divestiture, 2021-05-17), explicitly scored as expected
`NOT_DISCOVERED` against the current pattern, with the reason documented
in the gold file itself rather than left as an unexplained miss. Gold
blindness PARTIAL -- an AT&T 10-K excerpt and press-release-quoting
aggregator pages appeared in the same search as the independent sources;
the real 8-K text was fetched afterward, for diagnostic testing.

`data/eval_raw/att_real.json` -- the Item 1.01 announcement, included
deliberately even knowing it won't recall: this text IS reachable (a
real, standalone Item 1.01 filing, no item-filter issue here), so the
expected non-recall is a genuine pattern-coverage gap worth having on
record, not an unreachability exclusion like Six Flags/Ford/Brinker/AIG.

## Current aggregate (9 companies with raw data; Brinker/Ford still skipped)

9/26 (34.6%), 95% CI [0.19, 0.54].

## How to resume

```bash
python3 -m pytest tests/                          # confirm 229/229
cd code/eval && python3 run_coverage_eval.py --gold lumen.json disney.json tenable.json six_flags.json paramount.json brinker.json ford.json tesla.json aig.json netflix.json att.json
```

Next candidate work, in rough priority order:
1. A dedicated Reverse-Morris-Trust / spin-off-and-merge `DIVESTED_
   BUSINESS` pattern for AT&T's shape -- real, complex, and now has a
   validated real-text fixture (`att_real.json`) sitting ready for it.
2. Widen the `AGREED_TO_ACQUIRE` trigger to handle "entered into certain
   definitive agreements ... including (1) X" -- a bigger structural
   change than the curated-adjective-list fixes so far.
3. Refetch Lumen's real Brightspeed/Stonepeak/Colt divestiture text (not
   currently in the fixture at all) to see whether the new
   `DIVESTED_BUSINESS` pattern -- built for a direct asset-sale shape --
   generalizes to those, or surfaces yet another phrasing variant.
4. The registrant-self-reference generalization from the Tesla pass --
   still the single highest-leverage open item for cross-filing recall.
5. The item-filter revisit -- four real companies confirmed so far.
6. Run the real GLEIF gazetteer backend against the real 3.39M-row index,
   per `CONTEXT_EVENT_EXTRACTION_GAZETTEER.md`'s validation checklist.
