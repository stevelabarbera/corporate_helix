# Corporation Helix — State Filings Decisions Log

Mirrors the format of `docs/DECISIONS_EDGAR_MA.md` and
`docs/DECISIONS_GLEIF.md`: one ADR per real architectural decision or bug
fix on the state-level filing side, in chronological order, each
self-contained enough that neither a human nor a future AI session has to
reconstruct the reasoning from chat history.

---

## ADR-STATE-001 — First Certificate of Merger extractor; a third structured evidence source alongside EDGAR and GLEIF

**Date:** 2026-10-09
**Status:** Accepted

### Context

EDGAR depends on a federal securities filer existing on at least one side
of a transaction. GLEIF Level 2 relationship reporting is not mandatory
outside the derivatives regime, and is entirely absent for private-to-
private M&A (confirmed directly: the Dokobit UAB / Signicat AS
acquisition has both companies present and ACTIVE at GLEIF Level 1, but
zero relationship records at Level 2 — see the "private-company M&A
coverage gap" investigation in `CORPORATION_HELIX_CONTEXT_2026-08-28.md`).

A Delaware (or other state) Certificate of Merger is filed with the
Secretary of State at the moment a merger becomes legally effective. For
a public-company deal this is very often the same closing event an 8-K
Item 2.01 reports days to weeks later. For a private-to-private deal it
may be the only structured record that exists anywhere, public or
otherwise. Two concrete gaps this closes:

1. A state filing can predate the matching SEC disclosure by weeks —
   earlier signal on the exact same transaction.
2. A state filing covers private-to-private mergers EDGAR and GLEIF
   Level 2 both structurally cannot see.

No general bulk feed exists for Certificates of Merger (Delaware's
Division of Corporations is a paid, per-name lookup system, not a
crawlable or batch-queryable source), so per the project's architectural
rule this is, and will stay, an ingest-only source: Helix never fetches a
certificate, only parses one already in hand (a paste, an upload, an 8-K
exhibit someone already retrieved) — same boundary `whois_parser.py`
applies to WHOIS output and `ingest_supplied_evidence.py` applies to
ASM-supplied observations.

### What was built

`code/parsers/state_filing_extractor.py` — a structured-field extractor,
not an ensemble. Unlike 10-K/8-K prose, a Delaware Certificate of Merger's
numbered-paragraph structure (FIRST/SECOND/THIRD/...) is fixed by DGCL
Sec. 251, so a single well-anchored pattern set is the right tool here in
a way it would not be for `edgar_ma_extractor.py`'s free narrative text.
Extracts: surviving entity, merging (non-surviving) entity, constituent
jurisdictions, DGCL section cited, effective date/basis, executed date,
filing stamp if present.

`code/providers/state_filing_provider.py` — wraps the parsed result into
the same `ProviderResult` / `EntityCandidate` / `RelationshipAssertion` /
`Evidence` shape `GleifRelationshipRecordAdapter` already emits, so a
future fusion layer can consume EDGAR, GLEIF, and state filings uniformly
without a provider-specific special case. Reuses EDGAR's own
`MERGED_INTO` predicate rather than inventing a new one for the same
real-world relationship. Carries the same `corporate_relationship_
confidence` / `infrastructure_attribution_confidence` split used
everywhere else in the codebase, plus a `signal_precedence:
pre_disclosure` attribute making explicit that this source's value is
being early, not just being another relationship record of unspecified
recency.

Pattern set was built and validated against two real filed Certificates
of Merger pulled from their SEC 8-K exhibits (not written from memory of
DGCL boilerplate):
- Axion Acquisition Corp. / Axion International, Inc. (2008)
- Allis-Chalmers Energy Inc. / Wellco Sub Company (2011)

### Three real bugs caught during test-driven development

All three are documented in `state_filing_extractor.py`'s own comments;
summarized here because they're generalizable lessons, not just fixed
typos:

1. **Punctuation-terminal ambiguity truncated names.** A capture bounded
   by a consumed `[.,;]` terminal always loses the trailing period of a
   corporate suffix ("Inc.", "Corp.") to the terminal rather than the
   name, because "." is also a valid character inside the name itself —
   same bug shape, different cause, as the EDGAR "Ltd." truncation fixed
   earlier in `edgar_ma_extractor.py`. Fixed by bounding on a lookahead
   instead of a consumed terminal.

2. **Single-newline word-wrap broke a multi-line entity name**, the exact
   same bug class as the real Ford 10-K header-bleed case that produced
   `edgar_ma_extractor.py`'s `_JOIN` pattern — confirmed here by a test
   fixture that happened to wrap a company name across a line break.
   Fixed with a `_dewrap()` preprocessing pass (join single newlines,
   preserve blank-line paragraph breaks) rather than rebuilding `_JOIN`'s
   word-by-word approach, since this extractor matches structured fields
   rather than one shared entity grammar.

3. **An inline jurisdiction clause bled into the captured name** when a
   real filing states naming and jurisdiction in one sentence ("the name
   of the surviving corporation is X, a Delaware corporation") rather
   than splitting them into separate numbered paragraphs the way both
   original reference filings do it — caught by stress-testing against a
   third, invented phrasing variant before trusting the pattern set, not
   by either of the two real filings used to build it. Fixed by giving
   the name capture two alternative stopping points (line-end OR an
   inline jurisdiction clause) in one lookahead instead of just one.

### A pre-existing stale cross-reference, noted but not touched

`ingest_supplied_evidence.py`'s docstring cites `CORPORATION_HELIX_
CONTEXT.md sec 34.3` for the "Helix does not fetch evidence itself" rule.
As of this writing, section 34.3 is the 12-company saturation probe
order, not the architectural boundary — the citation appears to have
drifted after a later renumbering. `state_filing_extractor.py`'s
docstring states the rule by pointing to `whois_parser.py`'s own
docstring (which states it without a brittle section-number citation)
rather than propagating the stale reference into a second file. Worth a
one-line fix in `ingest_supplied_evidence.py` at some point; out of scope
for this change.

### Consequence

A fourth structured evidence source is now available in the same shape
as GLEIF and EDGAR, ready for the eventual fusion/virtual-analyst layer.
Not yet wired into any CLI entry point or tested against a real Target
(or other saturation-cohort) Certificate of Merger — next step is finding
one, the same way the EDGAR gold-eval cohort was built from real company
data rather than synthetic fixtures alone.

---

## ADR-STATE-002 — DBA / trade-name support deferred as a separate alias layer, not folded into `identity_key()`

**Date:** 2026-10-09
**Status:** Accepted (design decision; not yet implemented)

### Decision

A "doing business as" / trade name is a different string for the same
legal entity, not a normalization variant of its legal name the way
"Walt Disney Co" and "The Walt Disney Company" are. `identity_key()` in
`providers/edgar_resolver.py` normalizes legal-name spelling variants;
mixing DBA handling into it risks corrupting logic ADR-EDGAR-005 through
010 already spent real effort hardening on exactly this kind of edge
case.

Plan (not yet built): add a `trade_names: list[str]` field to the live
`models/entity.py` `EntityCandidate` — structurally identical to the
existing `former_names` field but semantically distinct (concurrent vs.
historical name). Consulted as a fallback match path only when
`resolve_cik_by_name()` / `identity_key()` fails to resolve a raw name,
never baked into the normalizer itself.

### A landmine identified, not yet cleaned up

Two unrelated `EntityCandidate` classes exist in this repo:
`code/models/entity.py` (the package, actually live in the GLEIF/EDGAR
provider pipeline) and `code/models.py` (a flat file, used only by
`resolution/matcher.py` and `cli.py`, which appears to be an earlier,
disconnected MVP). The stale flat-file version already has an
`other_names` field. Any future `trade_names` work should build on the
live package version and not accidentally resurrect the orphaned one —
easy to do by mistake given how close the two paths look. Not touched
here; noted for whoever picks up the DBA work.

### Status

Design-only. Target's own history (Dayton-Hudson Corporation trading as
"Target" for decades before its 2000 formal rename) is a natural first
test case once this is built, using data already in hand from the
ongoing Target validation work.
