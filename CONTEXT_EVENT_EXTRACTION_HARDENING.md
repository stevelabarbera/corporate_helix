# CONTEXT ADDENDUM — EDGAR M&A Trust-Boundary Hardening

**Date:** 2026-09-13

This addendum is part of the EDGAR M&A historical context. Keep it with
`CONTEXT_EVENT_EXTRACTION.md` and `docs/DECISIONS_EDGAR_MA.md`.

## Why this hardening pass happened

A code review after the first real coverage work found that the extraction
architecture was directionally strong, but the production trust boundary was
too permissive.

The key problem was not "the parser is bad." The parser intentionally uses
heuristics in several recovery paths. The problem was that a completed parser
event immediately became `ACCEPTED/HIGH/pivot_eligible=True`, allowing a
heuristic conclusion to recursively expand the Helix graph.

That violated the project's own principle that a false positive is more
expensive than leaving a candidate unresolved.

## Changes made

1. **Parser output is now candidate evidence by default.**
   `EdgarMAExpansionProvider` emits parser-discovered counterparties as
   `REVIEW/MEDIUM`, `pivot_eligible=False`.

2. **Recursion requires a separate trust decision.**
   An explicit `authorize_pivot_fn` is now the only route from parser
   candidate to `ACCEPTED/HIGH` recursive pivot.

3. **EDGAR evidence provenance is retained.**
   Facts preserve source text, extraction rule, subject/object, filing
   metadata, section SHA-256, parser ensemble details, organization votes,
   aliases, and the trust decision.

4. **Production extraction moved out of the benchmark.**
   Runtime extraction now lives in `code/parsers/edgar_ma_extractor.py`.
   `benchmark_m385_merger_coref.py` imports the production implementation.

5. **Silent ensemble fallback was removed.**
   Validated regex + spaCy + legal_rules mode is required by default.
   Degraded regex + legal_rules operation must be explicitly requested and is
   marked in evidence.

6. **SEC source provenance was improved.**
   The 8-K resolver now keeps `primary_document` and `document_url`.
   Its historical limitation is explicitly documented: it currently reads
   only `submissions["filings"]["recent"]`, so a date range does not imply
   exhaustive historical coverage.

## Important semantic rule going forward

> EDGAR event extraction can propose a company to investigate. Parser
> inference alone does not authorize that company to expand trusted ASM scope.

This is the same architectural separation used elsewhere in Helix:

`discovery -> evidence -> deterministic/adjudication trust decision -> graph pivot`

## Deliberately deferred

Do not accidentally mix these into this checkpoint when debugging it:

- HelixFact name-only -> LEI identity enrichment/dedup
- 10-K/10-Q document-wide locator
- SEC historical submissions files
- 8-K exhibit retrieval
- Disney cross-backend entity-boundary fusion

Those are still important, but each deserves its own measured change and
historical decision record.
