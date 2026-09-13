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
