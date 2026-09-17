# CONTEXT ADDENDUM — Bayer/Monsanto Test Pass: First-Person Self-Reference

**Date:** 2026-09-16

Part of the EDGAR M&A historical context. Keep alongside
`CONTEXT_EVENT_EXTRACTION.md`, `CONTEXT_EVENT_EXTRACTION_HARDENING.md`,
`CONTEXT_EVENT_EXTRACTION_DELL_EMC.md`, and the other company addenda
from this session (`_SIX_FLAGS`, `_PARAMOUNT`, `_BRINKER`, `_FORD`,
`_TESLA`, `_AIG`, `_NETFLIX`, `_ATT`), plus `_GAZETTEER`.

## Why this pass happened

Tenth company, second of three the user pulled from a "beautiful use
cases" list: "the Global Regulatory Divestiture: Bayer & Monsanto
(2016-2018)". DOJ required Bayer to divest ~$9B of assets to BASF --
"the largest merger divestiture ever required by the United States" --
alongside similar EU-mandated divestitures, as a condition of approval.
This pass found something more foundational than the divestiture
mechanism itself, though: a harder variant of the direction-ambiguity
bug found in the Dell/EMC pass.

## Bug 13 — FIXED: "Aktiengesellschaft"/"AG" was not a recognized corporate suffix

Real Monsanto 10-Q text names its acquirer "Bayer Aktiengesellschaft" --
German for "stock corporation" -- which was completely invisible to
entity extraction; no foreign corporate-form suffix had been supported
at all before this. Same shape as the earlier `L.P.` and `Co` suffix
fixes. **Fixed:** added `Aktiengesellschaft` and `AG` to the `CORP`
suffix alternation. Deliberately did NOT add other foreign suffixes
(GmbH, S.A., N.V., S.p.A., etc.) speculatively -- only the one actually
verified against real text this pass, consistent with this session's
discipline throughout (fix confirmed real gaps, don't guess ahead of
evidence).

## Bug 14 — FIXED: bare "we" self-reference with no named alias at all

Even with Bug 13 fixed, the text still produced zero events. Root cause,
distinct from anything found before: Monsanto's real 10-Q describes
itself being acquired using bare first-person "we" -- "we entered into
an agreement and plan of merger...with Bayer Aktiengesellschaft" -- and
**never names itself anywhere in the passage**, not even via an implicit
"(the 'Company')" definition. This is a harder version of the direction
problem found in the Dell/EMC pass: there, at least a named "the
Company" alias existed for the correction pass to work with; here there
is nothing to hang an alias on at all.

**Fix, in two parts:**

1. **Recognize "we entered into..." as `REGISTRANT_SELF_REFERENCE`.**
   Mirrors the already-existing convention used for the "we acquired X"
   10-K declarative pattern (built for Tenable, long before this
   session) -- this is the exact registrant-self-reference generalization
   flagged as the top open item back in the Tesla pass, now actually
   implemented for a second real pattern. Checks whether the text
   immediately before the trigger phrase is bare "we " and, if so, uses
   `REGISTRANT_SELF_REFERENCE` as the acquirer, the same placeholder the
   10-K pattern already uses.
2. **Let `MERGED_INTO`/`SUBSIDIARY_OF` resolve a generic, undefined
   "(the) company" self-reference too**, not just an explicitly-defined
   alias. Without this, the direction-correction pass built for EMC
   (Bug 10) would have nothing to work with here: "with the company
   continuing...as a wholly owned subsidiary of Bayer" never defines
   "company" as an alias anywhere in this text, so the existing
   correction mechanism couldn't fire. Added an implicit `"company" ->
   REGISTRANT_SELF_REFERENCE` mapping to the alias-resolution table used
   by those two patterns, **only when "Company" isn't already an
   explicitly-defined alias** -- never overrides a real, named entity
   (Six Flags, Disney, AIG, and every other company where "the Company"
   is explicitly defined keep working exactly as before). Also fixed a
   related bug found while wiring this in: `SUBSIDIARY_OF`'s own
   resolution step used the original `aliases` dict directly, not the
   lowercased table the new implicit mapping was added to -- so the
   first version of this fix still leaked the literal word "company"
   through as a fake entity name instead of resolving it. Fixed by
   consulting the correct table first.

**Verified end-to-end, both events correct:**

```
AGREED_TO_ACQUIRE  Bayer Aktiengesellschaft -> REGISTRANT_SELF_REFERENCE  COMPLETED
SUBSIDIARY_OF      REGISTRANT_SELF_REFERENCE -> Bayer Aktiengesellschaft  PROPOSED
```

Also confirmed `other_party()` (in `edgar_ma_provider.py`) already
handles `REGISTRANT_SELF_REFERENCE` correctly on either side of an event
-- no changes needed there. Full suite: 234/234 (232 baseline + 2 new
tests). Verified through the eval harness: `baymon-1` recalls correctly
with the right direction. No regressions to any other company's score.

## A structural note: this text is a 10-Q, not an 8-K

Unlike every other real fixture built this session, this text came from
Monsanto's own **10-Q**, not an 8-K -- and this project's fetcher
currently only pulls 8-K Item 1.01/2.01 text. So this specific real
disclosure would not be reachable by the live pipeline today, the same
class of gap as Brinker's and Ford's 10-Q-only disclosures. Included in
the fixture anyway, deliberately, because it's what actually surfaced
and validated the fix in this pass -- but worth being clear that this
fix's value depends on the still-outstanding 10-K/10-Q fetcher to
matter in live operation, same as several other findings this session.

## New gold + raw fixtures

`data/eval_gold/bayer_monsanto.json` -- 2 events (announced 2016-09-14,
closed 2018-06-07), scored from Monsanto's own perspective. The BASF
divestiture itself (a real, separate `DIVESTED_BUSINESS`-shaped event
from Bayer's side) is out of scope for this pass -- worth a dedicated
look given the complexity already flagged for AT&T's own unresolved
Reverse-Morris-Trust `DIVESTED_BUSINESS` gap. Gold blindness PARTIAL --
a real, verbatim excerpt of this same 10-Q text appeared in the same
search as the independent news sources; that excerpt is what was used to
build and validate the fix, deliberately not to write the gold events.

`data/eval_raw/bayer_monsanto_real.json` -- the 10-Q text only, no
closing text fetched this pass.

## Current aggregate (11 companies with raw data; Brinker/Ford still skipped)

10/30 (33.3%), 95% CI [0.19, 0.51].

## How to resume

```bash
python3 -m pytest tests/                          # confirm 234/234
cd code/eval && python3 run_coverage_eval.py --gold lumen.json disney.json tenable.json six_flags.json paramount.json brinker.json ford.json tesla.json aig.json netflix.json att.json dell_emc.json bayer_monsanto.json
```

Next candidate work:
1. One more company from the user's "beautiful use cases" list is
   queued: Broadcom/VMware ("Multi-Tranche Platform Integration",
   2022-2023).
2. The Bayer-side BASF divestiture text (real, real ~$9B deal) would be
   a good next real test of the `DIVESTED_BUSINESS` pattern, alongside
   AT&T's still-unresolved Reverse-Morris-Trust shape.
3. Everything already queued from prior addenda: the item-filter
   revisit, the real GLEIF gazetteer validation pass, re-diagnosing
   Lumen's divestitures once real text for them is fetched.
