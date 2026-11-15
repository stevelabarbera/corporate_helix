# Corporate Helix — Documentation audit and consolidation register

**Audit date:** 2026-11-15  
**Scope:** First-pass review of repository planning, context, handoff, and architecture documents on `main`. This is an indexed review of the documents below, **not** a claim that every Markdown file or every historical assertion has been exhaustively reconciled. No legacy files were deleted or renamed.

## Authority model (effective going forward)

1. [PROJECT_STATUS.md](PROJECT_STATUS.md) — current project state, active milestone, session handoff.
2. [BACKLOG.md](BACKLOG.md) — queued work and detailed findings, including the 10-item identity-resolution milestone.
3. Decision records (`DECISIONS_*.md`, other contracts) — canonical rationale for accepted architectural rules. Do not rewrite historical decisions; add superseding records when necessary.
4. Historic `CONTEXT*.md`, `CORPORATION_HELIX_CONTEXT*.md`, and `ROADMAP.md` — useful milestone snapshots, **not** live status authority. Their internal claims of being “current” or “source of truth” are historical.

## Reviewed document inventory

| File | Historical focus / retained value | Disposition |
| --- | --- | --- |
| [ROADMAP.md](../ROADMAP.md) | Early M1 corporate attribution resolver, normalization, ASM integration and demo phases; dated GLEIF validation notes | Historical roadmap; cross-check unchecked tasks against code before reopening |
| [CONTEXT.md](../CONTEXT.md) | Original pitch, evidence-based graph quality criteria, early parking lot and `make status` handoff convention | Historical vision and workflow |
| [CONTEXT copy.md](../CONTEXT%20copy.md) | August EDGAR v4/Sony validation and provider/normalization milestones | Historical handoff; no longer current |
| [CORPORATION_HELIX_CONTEXT.md](../CORPORATION_HELIX_CONTEXT.md) | Large evolving handoff covering M1–M4, M&A saturation and infrastructure track; later sections override earlier ones | Valuable historical record; do not rely on the first “current milestone” label |
| [CORPORATION_HELIX_CONTEXT_2026-08-19.md](../CORPORATION_HELIX_CONTEXT_2026-08-19.md) | M3.8 temporal M&A checkpoint, Broadcom/VMware validation | Frozen historical checkpoint |
| [CORPORATION_HELIX_CONTEXT_2026-08-28.md](../CORPORATION_HELIX_CONTEXT_2026-08-28.md) | M4.2 GLEIF L2→L1 enrichment and private-to-private M&A coverage gap | Historical checkpoint, later edits present |
| [M4.3C_HANDOFF_ADDENDUM.md](M4.3C_HANDOFF_ADDENDUM.md) | Recursive expansion: accepted/high-confidence/pivot-eligible facts only; Sony zero-seed baseline | Retain as milestone contract |
| [DECISIONS_GLEIF.md](DECISIONS_GLEIF.md) | CLI wiring regressions despite code being “built”; need end-to-end reruns after patches | Authoritative decision log |
| [DECISIONS_EDGAR_MA.md](DECISIONS_EDGAR_MA.md) | Parser inference must not authorize recursion; provenance, extraction, evaluation and guardrail history | Authoritative decision log |
| [DECISIONS_EDGAR_LONGFORM_LOCATOR.md](DECISIONS_EDGAR_LONGFORM_LOCATOR.md) | Long-form filing candidate locator is recall-oriented, not proof; document provenance | Authoritative decision log |
| [DECISIONS_STATE_FILINGS.md](DECISIONS_STATE_FILINGS.md) | Certificate of Merger extractor; deferred DBA/trade-name layer and duplicate EntityCandidate model pitfall | Authoritative decision log |
| [M43E_EVIDENCE_CONTRACT.md](../M43E_EVIDENCE_CONTRACT.md) | Corporate intelligence/ASM boundary; evidence requests and LLM suggestions cannot be trusted pivots | Retain as architectural contract |
| [GETTING_STARTED_MVP.md](../GETTING_STARTED_MVP.md) | Early working-slice instructions and commands; some paths may now be stale | Historical getting-started; verify commands before reuse |
| [BACKLOG.md](BACKLOG.md) | EDGAR coverage and extraction gaps, frozen-baseline findings, state filings, current identity milestone | Live detailed queue |

Additional variants such as `CORPORATION_HELIX_CONTEXT_2026-08-28 copy.md`, event-extraction context files, and other README/handoff files should be inventoried and compared in a subsequent exhaustive pass; this table does not assert full coverage.

## Important pitfalls and architectural decisions surfaced

1. **Do not recursively expand guesses.** EDGAR parser events and LLM suggestions are candidates until separately adjudicated; only trusted, accepted, high-confidence, pivot-eligible facts enter the next frontier. See ADR-EDGAR-001, M4.3C addendum and M43E contract.
2. **Do not conflate identity with ownership.** The current Sempra Energy → SEMPRA ENERGY TRADING LLC → NatWest failure is the concrete regression target; a true ownership path does not establish the queried seed identity.
3. **Preserve provenance and evidence.** Keep source documents, identifiers, relationship type, confidence and decision trace rather than converting all matches to unqualified subsidiaries.
4. **“Built” does not mean “wired or validated.”** ADR-GLEIF-001/002 record functionality lost or disconnected through integration changes. Validate known-good CLI commands and tests after patches.
5. **Separate retrieval coverage from parser quality.** A missing filing is not an extractor failure. Preserve frozen M&A baselines and avoid mixing coverage misses into extraction accuracy.
6. **Avoid premature ASM scope promotion.** Corporate Helix generates attributable, reviewable corporate/infrastructure candidates; the ASM system remains the main infrastructure collector. A network operator is not automatically the asset owner.
7. **Temporal and private-company blind spots matter.** EDGAR public-filer coverage and GLEIF Level 2 reporting leave gaps, including private-to-private M&A; state merger filings provide a complementary source.
8. **Do not collapse distinct relationship types.** Parent/subsidiary, acquisition, former ownership, alias/DBA, and infrastructure operator assertions require separate semantics.

## Conflicts and follow-up reconciliation

- **Competing “source of truth” declarations:** `CONTEXT.md` and several `CORPORATION_HELIX_CONTEXT*.md` documents call themselves the current handoff. Resolve operationally by pointing new sessions to `PROJECT_STATUS.md`; leave historical text intact.
- **Multiple “current milestone” labels:** Older roadmap/context headers identify M1, M3.8, M4.2, or M4.3B as active. They are dated snapshots, not evidence that current work regressed.
- **Old unchecked tasks may be completed:** Do not automatically carry every unchecked item from `ROADMAP.md` into the live backlog. Compare with current code, tests, and commit history first.
- **Tests vs reported milestones:** Some ADRs document historical local passing suites. They are not proof of the current checkout's test status; rerun tests.
- **Source file copies:** Similar context filenames and “copy” variants may diverge. Compare them before any deduplication or archival action.

## Remaining audit work

- [ ] Inventory **all** Markdown documents, including event-extraction context, code READMEs, and copied variants, not just search-discovered planning files.
- [ ] Diff context snapshots and identify unique decisions, pitfalls, and previously unrecorded deliverables.
- [ ] Cross-check old milestone completion claims against current code, tests, branches and merged PRs.
- [ ] Reconcile older unchecked tasks with the current backlog without losing parked research.
- [ ] Add explicit supersession pointers to historical documents (after review), without deleting historical evidence.
- [ ] Recheck the identity benchmark's ground-truth status and Sempra regression implementation against the active branch.

**Next implementation work remains:** Sempra regression → configurable identity scoring → minimal safeguards → explainable decisions. This documentation audit must not silently change experimental baselines or resolver policy.
