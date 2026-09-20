# EDGAR M&A Architecture Decisions

This file records **why** trust, evidence, and recursion behavior changed.
It is intentionally historical. Do not remove older decisions merely because
the implementation evolves; add a new decision that supersedes the old one.

---

## ADR-EDGAR-001 — Parser inference does not authorize recursive graph expansion

**Date:** 2026-09-13  
**Status:** Accepted

### Previous behavior

`EdgarMAExpansionProvider` converted every `COMPLETED` parser event directly
into a `HelixFact` with:

- `status="ACCEPTED"`
- `confidence="HIGH"`
- `pivot_eligible=True`

The iterative expansion engine then treated that inferred counterparty as a
trusted frontier node and recursively queried it.

### Why this changed

The parser intentionally contains heuristic recovery paths, including
"nearest prior organization" and "earliest organization after the clause."
Those are useful for candidate generation, but they are not equivalent to
identity-grade evidence.

In Helix, a false positive is especially expensive because a wrong legal
entity can recursively expand into additional corporate entities, domains,
ASNs, certificates, and eventual ASM scope.

### Decision

A completed EDGAR parser event is now a **candidate**, not an authorization.

Default output:

- `status="REVIEW"`
- `confidence="MEDIUM"`
- `pivot_eligible=False`

A separate `authorize_pivot_fn` must explicitly approve the candidate before
it becomes `ACCEPTED/HIGH` and may re-enter the recursive frontier.

### Consequence

Discovery recall remains visible, but parser inference alone cannot mutate the
trusted graph frontier.

### Tests locking this behavior

- parser candidates are REVIEW/non-pivot by default
- a default candidate cannot produce a second recursive hop
- explicit authorization still permits multi-hop recursion

---

## ADR-EDGAR-002 — Event-level source provenance must survive extraction

**Date:** 2026-09-13  
**Status:** Accepted

### Previous behavior

`infer_events()` generated an evidence fragment, but
`EdgarMAExpansionProvider` discarded it. The emitted fact retained accession,
filing date, item, event type, and pivot name, but not the exact source
fragment, parser rule, subject/object, ensemble details, or section identity.

### Why this changed

Helix's evidence model is intended to be inspectable and non-destructive.
When an extraction is later questioned, an analyst must be able to answer:

- what filing produced this?
- what text supported it?
- what rule produced it?
- what entities did the parser actually infer?
- what ensemble/configuration was running?

Without that information, debugging requires re-fetching/re-running and may
not reproduce the original state.

### Decision

EDGAR M&A evidence now retains:

- accession, filing date, form, item
- primary document and document URL when available
- extracted subject/object
- exact source evidence fragment
- extraction rule
- SHA-256 of the parsed section
- parser ensemble mode/backends/weights/threshold
- organization votes and resolved aliases
- explicit trust-decision metadata

### Consequence

A Helix fact carries enough provenance to understand how it was produced even
when parser behavior later changes.

---

## ADR-EDGAR-003 — Production owns extraction logic; benchmark imports production

**Date:** 2026-09-13  
**Status:** Accepted

### Previous behavior

`EdgarMAExpansionProvider` dynamically loaded
`benchmark_m385_merger_coref.py` from a filesystem path using `importlib`.

### Why this changed

A benchmark is an evaluation consumer, not a production dependency. When
production imports benchmark code:

- experimental and runtime concerns become coupled;
- the dependency direction is backwards;
- future benchmark edits can silently change production behavior;
- packaging becomes unnecessarily fragile.

### Decision

The extraction implementation lives in:

`code/parsers/edgar_ma_extractor.py`

Both production provider code and the M3.8.5 benchmark consume that module.

### Consequence

There is one production implementation of extraction behavior and the
benchmark measures that implementation.

---

## ADR-EDGAR-004 — No silent parser-ensemble degradation

**Date:** 2026-09-13  
**Status:** Accepted

### Previous behavior

If spaCy or its model failed to initialize, the provider caught any exception
and silently switched from the validated 3-backend ensemble:

`regex + spaCy + legal_rules`, threshold `1.5`

to a different 2-backend algorithm:

`regex + legal_rules`, threshold `1.0`

### Why this changed

The same filing could produce different trusted facts depending on machine
configuration. Worse, a programming error during backend initialization could
be mistaken for "spaCy unavailable."

That is incompatible with a deterministic trust boundary.

### Decision

Validated mode is required by default. If it cannot initialize, initialization
fails loudly.

A caller may deliberately request `allow_degraded_parser=True`; that state is
recorded in evidence as `EXPLICIT_DEGRADED_2_BACKEND`.

### Consequence

Algorithm substitution can no longer happen invisibly.

---

## ADR-EDGAR-005 — `identity_key` strips a leading "The" article

**Date:** 2026-09-19
**Status:** Accepted

### Previous behavior

`identity_key()` in `code/providers/edgar_resolver.py` stripped a trailing
corporate suffix (`corp`, `inc`, `co`, `llc`, `ltd`, `plc`, ...) but never a
leading article. `resolve_cik_by_name()` matches a study/gold company label
against SEC's live `company_tickers.json` by exact `identity_key` equality.

### Why this changed

The M&A-S1 saturation baseline run against Disney (`ma_saturation_pilot_v1.json`,
company id `disney`) produced a total `CIK_RESOLUTION_MISS` — all 4 gold
events unresolved — even though Disney's current CIK (1744489) is a live,
correctly-covered entity. Root cause: EDGAR's own registrant name for CIK
1744489 is **"Walt Disney Co"** (no "The", "Co" not "Company"), while the
study's company label is **"The Walt Disney Company"**. Before this fix:

```
identity_key("The Walt Disney Company") -> "the walt disney"
identity_key("Walt Disney Co")          -> "walt disney"
```

These never match, so the resolver returns `None` for an entity that is
otherwise trivially resolvable.

### Decision

`identity_key()` now also strips a leading `"the "` article (anchored to the
start of the string only, so a mid-name "the" — e.g. "Bank of the West" — is
left untouched). See `tests/test_edgar_resolver_identity_key.py`.

### Consequence

Any company whose gold/study label uses "The X Company" but whose current
EDGAR registrant name drops the article (a common EDGAR normalization) now
resolves correctly. For Disney specifically, this is only a partial fix —
see the CIK-successor follow-up below, which this ADR does **not** address.

---

## ADR-EDGAR-006 — `identity_key` strips stacked corporate-form suffixes, and a mislabeled failure class

**Date:** 2026-09-20
**Status:** Accepted

### Previous behavior

`_SUFFIX_RE` stripped exactly one trailing corporate-form word (`corp`,
`inc`, `co`, `llc`, `ltd`, `limited`, `plc`, `company`) and stopped.

### Why this changed

The M&A-S1 saturation baseline recorded `ENTITY_RECOGNITION_MISS` for
Lumen's Colt Technology Services divestiture (`lumen-5`, deepest stage
`LOCATOR_CAPTURED`). Running the actual validated 3-backend extraction
ensemble (`EdgarMAExtractor`, regex + spaCy + legal_rules) directly against
the cached 8-K Item 2.01 text showed this was **not a real NER failure**:

```
orgs: ["Colt Technology Services Group Limited", "Lumen Technologies, Inc."]
org_votes: {"Colt Technology Services Group Limited": 2.75, ...}
```

2.75 is well above the 1.5 acceptance threshold — the org was correctly
found and scored. The actual failure was one step later, in the evaluator's
`same_company()` / `identity_key()` exact-match check:

```
identity_key("Colt Technology Services Group Limited") -> "colt technology services group"
identity_key("Colt Technology Services")                -> "colt technology services"
```

A single suffix strip removed only the trailing "Limited" and left "group"
dangling, so an otherwise-correct extraction never matched the gold label.

**This means the M&A-S1 study's `ENTITY_RECOGNITION_MISS` failure class, as
currently measured, conflates two different problems**: cases where the NER
ensemble genuinely never found the org, and cases (like this one) where it
found the org correctly but the identity-matching step used to *score* the
study rejected a valid match. Anyone reviewing saturation-study frequency
counts for this failure class should keep that distinction in mind —
Alsid SAS (Tenable, `LOCATOR_CAPTURED`) shows the identical stage pattern
and is a strong candidate for the same root cause, though this was not
independently confirmed against real filing text (no cached raw 8-K text
for Alsid exists in this repo — see follow-up item 7 below).

### Decision

Suffix stripping in `identity_key()` is now applied iteratively (loop until
no more trailing corporate-form word matches, instead of stripping once),
and `group`/`holding(s)` were added to the stripped-suffix vocabulary.
Verified against real company names (Alphabet Inc., Fox Corporation,
Northrop Grumman Corporation, Kraft Heinz Company, Blackstone Group Inc.,
Apollo Global Management, Inc.) to confirm no over-stripping of load-bearing
name words. See `tests/test_edgar_resolver_identity_key.py`.

### Consequence

`lumen-5` (Colt) now correctly reaches `ENTITY_RECOGNIZED`. Full test suite
re-run clean at 248/248 after also installing this repo's own declared
dependencies (`tldextract` — already in `pyproject.toml`, just not
installed in this environment; `pyahocorasick` — the optional `gazetteer`
extra) plus `spacy`+`en_core_web_sm`, which the validated ensemble requires
per ADR-EDGAR-004 but which is **not currently declared anywhere in
`pyproject.toml`** — worth adding as a base dependency (with a note that the
model itself needs a separate `spacy download` / wheel install, since spaCy
models aren't installable by plain package name from PyPI).

---

## Known follow-up decisions not included in this patch

These were deliberately kept separate to avoid mixing too many architectural
changes in one checkpoint:

1. **HelixFact identity/enrichment:** an EDGAR name-only fact and later GLEIF
   LEI enrichment currently become separate fact keys. Identity enrichment
   needs a first-class operation rather than ordinary dedup.
2. **Long-form EDGAR locator:** build a document-wide 10-K/10-Q candidate
   region locator, validated on the known Tenable 10-K evidence first.
3. **Historical SEC retrieval:** `fetch_8k_ma_filings()` currently reads only
   `submissions.filings.recent`; start/end dates are therefore not guaranteed
   exhaustive for prolific filers.
4. **Exhibit retrieval:** current 8-K fetch downloads the primary document
   only; acquisition evidence in exhibits remains a retrieval gap.
5. **Disney entity-boundary fusion:** regex/spaCy overlapping organization
   spans still split votes and need a principled canonicalization/fusion fix.
6. **Point-in-time CIK resolution for corporate successions** (deferred after
   ADR-EDGAR-005). `resolve_cik_by_name()` only queries SEC's *current*
   `company_tickers.json` snapshot — a live name-to-CIK map with no sense of
   time. That is structurally insufficient for a holdco flip / successor
   issuer, where the *same trade name* is worn by a *different CIK* at
   different points in time.

   Disney's saturation-baseline case (`data/eval_gold/disney.json`) is the
   concrete example and can be used as the test fixture when this is
   picked up — no need to re-derive it:

   | Gold event | Date | Filed under CIK | That CIK's name *at filing time* | That CIK's name *today* |
   |---|---|---|---|---|
   | disney-1 (original Merger Agreement) | 2017-12 | 1001039 | "The Walt Disney Company" | "TWDC Enterprises 18 Corp." |
   | disney-2 (Amended & Restated Merger Agreement) | 2018-06 | 1001039 | "The Walt Disney Company" | "TWDC Enterprises 18 Corp." |
   | disney-3 (Closing) | 2019-03-20 | 1744489 | "TWDC Holdco 613 Corp." | "The Walt Disney Company" |
   | disney-4 (Fox Sports Net divestiture) | 2019-08-23 | 1744489 | (renamed, post-close) | "The Walt Disney Company" |

   (Counterparty Twenty-First Century Fox, Inc. is CIK 1308161 and is not
   part of this problem — it resolves normally.)

   After ADR-EDGAR-005's leading-article fix, expect disney-3/disney-4 to
   resolve (CIK 1744489 is correctly named "The Walt Disney Company" *today*)
   but disney-1/disney-2 to keep failing `CIK_RESOLUTION_MISS` — CIK 1001039
   is no longer named "The Walt Disney Company" in any current-snapshot
   lookup, even though it legitimately was when those filings were made.

   **Fix requires a historical name index, not a live one** — e.g. pulling
   each CIK's `formerNames` array (with date ranges) from its own
   `submissions/CIK##########.json`, not just the live ticker file, and
   resolving by (name, as-of-date) rather than (name) alone.

   `code/resolution/resolver.py` (the GLEIF-side identity graph, not the
   EDGAR event-extraction path) already has a former-name-alias merge
   pattern (`_former_name_match`, `alias_type == "former_name"`) that is a
   reasonable design reference to port over rather than building from
   scratch — but it is a different subsystem and is not currently wired
   into `code/providers/edgar_resolver.py` at all.
7. **Alsid SAS (Tenable, `LOCATOR_CAPTURED`) not independently confirmed
   as the same identity-matching bug fixed in ADR-EDGAR-006.** Stage
   pattern matches Colt exactly, but no cached raw 8-K text for Alsid
   exists in this repo, so the extractor was never actually run against
   real Alsid filing text to confirm the org was found correctly and it's
   purely a naming-suffix mismatch (vs. a genuine NER miss). Fetch the
   real Alsid acquisition 8-K/10-K text and re-run
   `EdgarMAExtractor.parse_section()` on it directly before assuming this
   one is closed by ADR-EDGAR-006 too.
8. **spaCy is a hard requirement of the validated extraction ensemble
   (ADR-EDGAR-004) but is not declared anywhere in `pyproject.toml`.**
   A fresh `pip install -e .` leaves `EdgarMAExtractor()` raising
   "Validated EDGAR M&A ensemble unavailable" with no hint from the
   dependency manifest about what's missing. Add `spacy` as a base
   dependency, plus a README/install note that the `en_core_web_sm` model
   itself needs a separate download step (spaCy models aren't installable
   by plain package name from PyPI).
