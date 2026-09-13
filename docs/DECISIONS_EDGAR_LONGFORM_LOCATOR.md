# EDGAR Long-Form M&A Evidence Locator Decisions

Date: 2026-09-13

## Decision
Use a document-wide locator for long-form filings instead of assuming a single "Business Combinations" section.

Manual Tenable review showed that M&A evidence can appear in business-combination notes, tax notes, tables, and ordinary prose. The locator is recall-oriented and only selects candidate regions. It does not assert M&A truth.

## 10-K first, generic implementation
10-K is the first validated filing type. The locator accepts a `form` value and contains no 10-K-specific event logic so 10-Q can reuse it directly.

## Trust boundary unchanged
Locator-selected text still flows through the production extractor and produces REVIEW/MEDIUM, non-pivotable candidates by default. Explicit adjudication is still required before recursion.

## Provenance
Long-form evidence should retain filing accession/date/form, primary document and URL, locator version, region offsets, signal categories/hits, extractor source fragment, parser ensemble/votes, extraction rule, and trust decision.

## Known limitations
- only `submissions["filings"]["recent"]` is traversed
- only the primary filing document is fetched
- divestiture location is supported, but general divestiture extraction is still missing
- Disney entity-boundary vote fusion remains separate work
- HelixFact identifier enrichment remains separate work
