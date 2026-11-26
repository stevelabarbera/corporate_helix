# SEC–GLEIF relationship reconciliation V1

Status: **NEXT PRIORITY — design/implementation backlog, not implemented**  
Decision: pause company-specific SEC grammar tuning; increase source coverage and useful relationship discovery.

## Current code reality (verified 2026-11-26)

- `code/run_company_ma_expansion.py` runs both `EdgarMAExpansionProvider` and `GleifIdentityFallbackProvider` via `run_expansion()`. This is *provider co-execution*, not event/relationship reconciliation.
- `code/providers/gleif_identity_fallback_provider.py` calls `resolve_company_root()` and emits an accepted, pivot-eligible fact for the **root legal entity** only when resolution is AUTO_RESOLVED. No separate direct-parent, historical-period, or transaction event is emitted.
- `code/eval/run_ma_s1_baseline.py` intentionally measures EDGAR only; four-company benchmark did **not query GLEIF**, so negative SEC sentinel results do not imply a GLEIF failure.
- `code/root_entity_resolver.py` supports an `as_of_date` parameter and enforces exact canonical legal-name anchoring before endorsing a root. Continue that conservative policy. Historical RR period flattening, stale ACTIVE statuses, and accounting-period effects are known upstream concerns; never treat apparent current status alone as proof of current ownership.
- The generic `HelixFact.identifier` is presently overloaded for identifiers: SEC audit pivot uses a 10-digit CIK while GLEIF fallback assumes a truthy identifier means a known LEI. **Require separate explicit CIK/LEI identity fields or typed identifiers** before stitching providers together. Do not silently interpret a CIK as an LEI or suppress GLEIF simply because a CIK is set.
- `run_expansion()` calls each provider for each pivot but only recurses on trusted/pivot-eligible new facts. A GLEIF-derived root can become a new pivot; this must not be misconstrued as evidence of an acquisition or that every root asset belongs to the originally queried company.

## V1 contract

Given a seed company and an `as_of_date`:
1. **Resolve identities** across available SEC CIK and GLEIF LEI, preserving queried entity, exact/ambiguous match status, and source provenance. Preserve unresolved entities; do not auto-pivot on lexical-only or ambiguous names.
2. **Run source discovery independently.** SEC event evidence and GLEIF L1/L2 relationship evidence both contribute even if one source finds zero events. Record `NOT_CHECKED`, `NO_MATCH`, `NO_EVIDENCE`, `ERROR`, `FOUND` separately for each provider.
3. **Preserve different edge types.** `ACQUIRED`, `AGREED_TO_ACQUIRE`, `MERGED_INTO`, `SUBSIDIARY_OF`, `DIRECT_ACCOUNTING_PARENT`, and `ULTIMATE_ACCOUNTING_PARENT` are not synonyms; never synthesize a historical M&A closing from an L2 parent relationship alone.
4. **Reconcile across identity, not strings alone.** A common LEI is strong identity evidence; names/aliases can suggest links but require verification where ambiguous. Reconcile acquirer/target roles, event dates versus relationship validity periods, and whether the relation is current or historical. Preserve conflicting evidence.
5. **Emit structured, explainable output.** For each entity and candidate link: source, accession or GLEIF RR record identifier, relationship type, source date, valid period start/end when present, observed snapshot, certainty, policy decision and unresolved/review reasons. Never collapse raw evidence into a single unsupported company-level flag.
6. **Output separate classes:** verified event, independently observed accounting relation, corroborated event/relationship, candidate for review, conflicting evidence, unresolved identity, not covered.
7. **Maintain safe ASM boundary.** A legally related entity is not automatically in-scope for active scanning or asset attribution. Keep explicit scope/ownership approval distinct from legal graph edges.

## First engineering slice (high leverage, minimal changes)

Create a **read-only, deterministic dual-source diagnostic** wrapping the existing SEC baseline output and calling the existing GLEIF resolver for each **seed and gold counterparty** (use `as_of_date` appropriate to the target event, plus current for comparison). No network re-fetch required for SEC results. Output side-by-side source coverage, identities and parent paths, with distinct `NOT_CHECKED` / `NO_MATCH` / `REVIEW_REQUIRED` / `AUTO_RESOLVED`; do not convert roots into acquisitions. This provides evidence whether GLEIF adds recall on GE/Alstom and Bayer/Monsanto **before** we attempt automated inference.

Then implement explicit typed CIK/LEI identities and relationship-edge records, adapt the two existing providers to emit/source-link these, and add resolver freshness/period integrity checks before any automatic cross-source corroboration.

## Acceptance gates

- Four-company benchmark plus independent positive/negative cases must show source coverage and GLEIF contributions without changing frozen EDGAR stage measurements.
- Works for no SEC result, no GLEIF result, both results, historical parent, expired parent, ambiguous same-name entity, and false common-name collision.
- No false `ACQUIRED` emitted from accounting consolidation; no acceptance/auto-pivot when exact identity or relationship-period freshness is missing.
- Tests exercise contradictory sources, as-of dates, typed CIK vs LEI, and no-data vs error distinction.
- Compare *net new defensible edges* and human review burden, not raw entity count.
- Do not resume company-specific SEC syntax tweaks unless multi-company coverage evidence justifies them.

## Deferred

- Additional SEC grammar fixes (including 2017 Monsanto direction) and GE/Alstom entity regex tuning.
- Any assumption that GLEIF covers every subsidiary/business-unit acquisition.
- Expansion into live ASM inventory without explicit scope validation.

## Immediate next work

Implement the read-only joint diagnostic first; inspect results for Monsanto/Bayer and GE/Alstom and record GLEIF coverage before promoting any new edge into the trusted graph.
