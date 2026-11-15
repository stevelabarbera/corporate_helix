# Helix backlog

## Master workstream index — M&A-first prioritization (2026-11-15)

**Product:** Given a company name, discover as comprehensively as practicable all relevant M&A transactions and related entities; provide evidence-backed corporate identities to downstream ASM. ASM owns network footprint discovery. See [PROJECT_STATUS.md](PROJECT_STATUS.md) for the authoritative mission and current handoff.

**Status labels:** Historical validation is not proof of current-branch integration. Before closing a task, verify the actual implementation, tests and (where applicable) live-source behavior. The detailed historical findings and acceptance criteria below remain in force.

| Workstream | Feature / deliverable | Priority | Disposition / current evidence |
| --- | --- | --- | --- |
| GLEIF | Level 1 ingestion, identity index, canonical entity matching | P0 | Historically validated; verify current pipeline |
| GLEIF | Level 2 relationship ingestion, endpoint enrichment, parent traversal | P0 | Historically validated; verify integration and semantics |
| GLEIF | Sempra wrong-seed/wrong-root regression; suspect SentinelOne roots | P0 | Active; regression not yet verified complete |
| GLEIF | Configurable evidence weights, thresholds, operating profiles | P0 | Planned; detailed tasks below |
| GLEIF | Non-bypassable identity-integrity safeguards and conflict handling | P0 | Planned; detailed tasks below |
| GLEIF | Decision explanations, source provenance, versioned scoring | P0 | Planned/partial; detailed tasks below |
| GLEIF | Independent labels for 30-company identity cohort and profile comparison | P0 | 30 executed, 0 independently scored |
| SEC coverage | Per-company filing manifest, source periods and skipped-form reasons | P0 | Built and cohort-run; verify live behavior |
| SEC coverage | Document, section and exhibit discovery; missing-form attribution | P0 | Partial; prioritize by measured yield |
| SEC coverage | Selective 425/S-4/F-4 and foreign-filer exhibit evaluation | P1 | Conditional research; do not indiscriminately fetch |
| SEC extraction | 10-K, 8-K, Exhibit 21 and foreign-filer transaction extraction | P0 | Implemented in parts; benchmark robustness |
| SEC extraction | Robust legal-language/event recognition beyond fragile keyword patterns | P0 | Open reliability gap; preserve provenance and event type |
| SEC extraction | Parser miss taxonomy: encoding, wrapping, aliases, counterparties, event grammar | P0 | Historical fixes plus unresolved cases |
| SEC extraction | Agreement vs closing vs divestiture and temporal transaction semantics | P0 | Partial; validate against independent disclosures |
| M&A integration | Reconcile SEC transactions and GLEIF entities without treating ownership edges as M&A events | P0 | Partial; end-to-end verification required |
| M&A integration | Trusted recursive expansion, historical names, acquired/merged entities | P0 | Historically validated; verify end-to-end |
| M&A integration | Private-to-private and inactive-filer/buyer-side discovery gaps | P1 | Known coverage gaps; targeted research |
| Evaluation | Independent known-transaction gold set and measured M&A recall | P0 | Incomplete; never equate candidate count with recall |
| Evaluation | Separate retrieval, section/exhibit, extraction and end-to-end failure metrics | P0 | Coverage manifest exists; full attribution pending |
| Evaluation | Frozen 12-company saturation cohort, regression tests, unseen holdouts | P0 | Partial; preserve historical baselines |
| Reliability | CLI smoke tests, reproducible indexes, data/source version tracking | P0 | Historical wiring regressions require verification |
| Delivery | Evidence-backed M&A inventory with identities, aliases, dates, confidence and provenance | P0 | Core MVP output; end-to-end validation pending |
| Delivery | ASM handoff of qualified corporate identity candidates (not fabricated hostnames) | P1 | Integration work; downstream ASM performs footprint discovery |
| Secondary | Broad corporate graph presentation and infrastructure attribution | P2 | Deprioritize unless needed for core M&A evidence |
| Secondary | State merger filings, DBA/trade names, new registries/provider adapters | P2 | Targeted exceptions; reconsider for measured source gaps |
| Secondary | Virtual analyst, LLM hypotheses, dashboards, customer UI | P2 | Optional enhancements; trust guardrails remain mandatory |
| Maintenance | Duplicate model cleanup, stale references, docs consolidation | P2 | Address when blocking development or causing regressions |

**Execution order:** Complete the Sempra regression and configurable GLEIF identity-resolution batch below; independently validate the current GLEIF pipeline; then prioritize SEC coverage and extraction fixes based on measured missed transactions. Do not reopen old unchecked tasks without checking code/tests. **No P0 label is a claim that implementation is complete.**


Parked work, each with the trigger that put it here and the condition for picking it up.
Last updated 2026-10-13. Decisions live in the `DECISIONS_*.md` files; this is only the queue.

## Foundation (do first -- decides whether the items below are worth doing)

Trigger: every new company has surfaced a document or format Helix missed (Alsid SAS, Einride/Flipturn).
Those misses are two different classes: *coverage gaps* (form never fetched: 6-K/20-F/40-F, older
filing pages) and *extraction failures on fetched documents* (the "AB" suffix, cp1252 quotes, hard-wrapped
lines). Fetching everything only fixes the first class, so the foundation is two pieces:

1. **Per-company coverage manifest.** *(Built: `code/providers/edgar_coverage.py`, `code/eval/coverage_manifest.py`,
   `code/eval/coverage_cohort.py`; first cohort run 2026-10-13 -- see the findings below.)* Enumerate every filing from the submissions metadata (incl.
   paginated `filings.files`) and record what Helix did with each: fetched / skipped + reason. Missing
   form families and date ranges then show up in a report instead of being found by hand. Metadata only,
   no bulk download. Prototype on Einride/Flipturn.
2. **Measured recall.** A list of known acquisitions from a source independent of Helix; report how many
   Helix finds. New misses add a row; fixes are proven against the list.

Only after both: a selective full-document loop over the form types the manifest shows are worth it.
Needs a networked machine (sec.gov is unreachable from the dev sandbox); the code and tests can be built
without it.

## Saturation study notes (frozen baseline -- annotate, do not edit results)

- **Trump Entertainment Resorts is a coverage test, not an extraction test.** Confirmed 2026-10-13 with the
  coverage manifest (`coverage_manifest.py --cik 943320`): CIK 0000943320 is the right entity, but all 662 of
  its filings fall between 1995-11-13 and 2013-03-20. It filed nothing in the 2015-2026 study window, so the
  2016 Icahn change of control (its only gold event) can never reach the extractor. The result file's
  `DISCLOSURE_NOT_IN_RETRIEVED_CORPUS` label is accurate. Keep this row out of any extraction-quality average.
  The baseline result is left untouched (frozen-baseline rule).
- **New test idea: buyer-side pivot.** A company that stops reporting is invisible to Helix by name; its
  acquisition is only findable in the *acquirer's* filings (here Icahn Enterprises L.P. -- look up and verify
  its CIK before use). Add as a separate new row, not a rewrite of the Trump row.
- **General lesson:** the manifest now flags `NO FILINGS IN WINDOW` (with earliest/latest dates) on the first run
  for any company in this state.

### First cohort run findings (2026-10-13, 12 companies, window 2015-2026)

Skipped deal-relevant forms, totals: 10-Q 315, DEFA14A 209, **425 76**, S-4 + S-4/A 27, 10-Q/A 4, SC TO-T(/A) 5.
- **Form 425 and S-4 are concentrated in the stock-merger companies** (425: Lumen 32, Intuitive Machines 21,
  Six Flags 13, Kraft Heinz 10; none elsewhere). Small volume, pre-closing signal -> first candidates for
  second-phase retrieval, together with F-4/DEFM14A.
- **10-Q (every company, ~35 each) and DEFA14A (routine proxy material) are high volume and likely low yield**
  -- deliberately not queued.
- **Unproven:** counts show where the forms are, not that they add events. Before building, run the extractor
  on a handful of 425/S-4 documents for Lumen, Six Flags, Kraft Heinz and see whether they surface events the
  gold lists miss.
- Einride AB (CIK 2095096): 79 filings, 12 retrievable (all 6-Ks, includes the Flipturn 6-K); 28 x 425 + F-4 + F-4/A
  appear to belong to its own listing transaction, not Flipturn (inferred from form types, unverified).

## EDGAR / foreign filers (from ADR-EDGAR-012 and its addendum)

| Item | Why parked | Pick up when |
|---|---|---|
| **6-K exhibit retrieval (EX-99.x press releases)** | Einride's 6-K body carried the deal summary, so not needed there. Many 6-Ks are stub covers that only say "see Exhibit 99.1" -- *frequency unmeasured*. | A sample of foreign-filer deal 6-Ks (run from a networked machine) shows stub bodies are common. Skip EX-2.1 (long contracts, names already in the body) unless bodies prove too thin. |
| **Gold entry `einride-1`** | Needs verbatim text already saved in `data/raw/einride/`. | Soon. Einride AB / Flipturn, Inc., AGREED_TO_ACQUIRE, agreement dated 2026-07-16. Do **not** label COMPLETED until a closing disclosure is found (Q3 2026 expected; a later 6-K). |
| **Closing check for Einride/Flipturn** | Only signing/announcement seen (6-K 2026-07-21). | Save the EX-99.1 press release or find the closing 6-K. |
| **8-K / 10-K hard-wrapped lines** | The source-line unwrap is gated to 6-K/20-F/40-F because 8-K `item_sections` keys on line-start headers and impact can't be measured offline. Likely affects some 8-Ks/10-Ks. | Networked cohort rerun can compare before/after; then consider enabling more broadly. |
| **Frozen-baseline cohort rerun (12 companies)** | The cp1252 decode fix touches every form (only filings that were not valid UTF-8). | From a networked machine, after current foundational work. |
| **Disk cache + rate limiter for retrieval** | Prolific 6-K filers mean many downloads; SEC limit ~10 req/s. | Before any bulk foreign-filer run. |
| **Second-phase forms** | 10-Q, S-4/F-4, 425, DEFM14A not retrieved. | After exhibit retrieval decision. |
| **Extractor noise** | Junk org `"Regulation S-K. The Company"` (sentence-boundary bleed from the Item 601(a)(5) footnote); stockholder-representative LLCs appear as org candidates; alias-less passages only get regex weight 0.5 < 1.5 threshold. | EVENT_GRAMMAR_MISS work. |
| **Lost-quote failure mode** | If quotes are lost (U+FFFD), the extractor can confidently pick the wrong counterparty (stockholder rep). Decode fix removes the production cause; a damaged copy can still trigger it. | Consider refusing/flagging text containing U+FFFD in alias-bearing passages. |

## State filings / identity (ADR-STATE-001/002)

- **DBA / `trade_names` on `EntityCandidate`** -- design only (ADR-STATE-002); consulted as fallback when `identity_key` resolution fails, not folded into `identity_key()`.
- **Shell recognition for reverse triangular mergers** in the Delaware Certificate of Merger extractor (currently yields sub -> target with no parent).
- **Wire `StateFilingProvider` into a CLI** and validate on a real Certificate of Merger.

## Other

- Newport News / TRW gold additions.
- Virtual analyst / semantic hypothesis layer (next milestone).
- M4.3A Sony confirmation run.
- Fix stale "sec 34.3" cross-reference in `ingest_supplied_evidence.py` (should point to `whois_parser.py` docstring).
- Clean up the two `EntityCandidate` classes (live `code/models/` package vs orphaned flat `code/models.py`).

## CrowdStrike audit follow-ups (ADR-EDGAR-013)
- **DONE (cadb0f7):** Split conjoined Onum/Pangea legal entities while preserving match positions and alias handling; 372 local tests passed.
- **Improved (ADR-EDGAR-013 rerun3):** SecureCircle alias added; CrowdStrike reached 10/11 candidate emissions. Broader identity-level vote pooling remains optional, not an active blocker.
- Gold hygiene: the Humio AGREED_TO_ACQUIRE duplicate row cannot be found in 10-Ks; decide whether announcement rows belong in 8-K/exhibit-only gold.
- Verify the 1 unmatched CrowdStrike candidate from rerun3 and the 9 new cohort candidates against filings. Do not treat parser output alone as confirmed acquisitions.
- Explain-miss: add a `--all` mode that loops gold rows so the shell loop is not needed.

## Configurable identity resolution and evidence validation (next milestone; 2026-11-14)

Trigger: 30-case identity benchmark completed without execution errors but all 30 cases remain NOT_SCORED pending independent ground truth. Sempra Energy was matched to SEMPRA ENERGY TRADING LLC and the ownership traversal proposed NATWEST GROUP PLC as a REVIEW_REQUIRED root. This is an incorrect proposed root for the intended query, even though the resolver did not auto-resolve it. Distinguish incorrect *recommendations* from incorrect *automatic decisions*.

**Design decision:** Evidence weights, acceptance/review thresholds, and operating profiles should be configurable at the highest level. Retain only a small set of narrowly scoped, non-bypassable identity-integrity requirements. Identity matching and ownership traversal are separate assertions: a real ownership edge does not prove the seed entity is the requested company. Keep exploratory leads visible, with provenance, rather than silently dropping them. Version each configuration and record the version with every decision.

### Immediate development batch (priorities 1–4)

1. [ ] **Sempra regression:** Query `Sempra Energy` must not treat `SEMPRA ENERGY TRADING LLC` → `NATWEST GROUP PLC` as verified identity or a supported corporate root. Retain the evidence as a flagged, investigatory lead. Assert both proposed-root correctness and decision status.
2. [ ] **Configurable scoring:** Externalize signal weights, penalties, and decision thresholds; validate config schema and supply conservative, balanced, and exploratory profiles. Initial weights are hypotheses, not calibrated accuracy claims.
3. [ ] **Minimal mandatory safeguards:** Require independently supported seed identity before an ownership path can justify auto-resolution; block automatic resolution on unresolved conflicting-root evidence. Make the hard rules explicit, narrow, and separately testable.
4. [ ] **Explainability/audit:** Emit per-signal contributions, penalties, evidence/provenance, safeguard outcomes, chosen profile/config version, and reasons for AUTO_RESOLVED / REVIEW_REQUIRED / NO_MATCH.

### Validation and integration (priorities 5–10)

5. [ ] Independently verify ground truth for the existing 30 benchmark cases; preserve PENDING/NOT_SCORED until verified.
6. [ ] Run the same frozen cohort under all three profiles; compare auto-resolution rate, review burden, proposed-root precision, and false positives once ground truth exists.
7. [ ] Investigate suspect parent selections, including Sempra and SentinelOne; add confirmed failures as regression cases.
8. [ ] Model temporal ownership explicitly (current, former, acquired, divested) and avoid treating historical paths as present-day control.
9. [ ] Connect verified identity and temporally qualified M&A relationships to downstream corporate/ASM discovery without silently promoting exploratory leads.
10. [ ] Run end-to-end MVP evaluation from evidence ingestion through identity, M&A relationships, and actionable ASM outputs.

**Acceptance criteria for first batch:** Sempra case cannot surface NatWest as a verified root; existing resolver tests remain green; all decisions expose reproducible score explanations; changing profiles changes permitted scoring/threshold behavior without bypassing identity safeguards. Do not interpret 0/30 scored as 0% accuracy or expand the benchmark for headline numbers before independent ground truth is established.
