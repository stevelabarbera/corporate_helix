# Corporate Helix — Project status and session handoff

**Last reviewed:** 2026-11-15  
**Current phase:** Identity-resolution quality and configurable evidence scoring  
**Next work item:** Sempra Energy regression test  
**Status convention:** This is a planning/handoff snapshot, not a claim that unverified local work or branches are merged.

## Foundational decision — customer-owned evidence and trust policy (2026-11-23)

See [ADR_CUSTOMER_EVIDENCE_TRUST_POLICY.md](ADR_CUSTOMER_EVIDENCE_TRUST_POLICY.md). **Customer-provided records are first-class evidence**; each organization controls authorized acceptance/review/corroboration policy within hard tenant and security boundaries. Distinguish raw claims, source authority, confidence, verification status, tenant-specific disposition and downstream permissions. Retain append-only auditable decisions with policy versions; do not equate a customer-accepted identity with independently verified ownership or approved ASM scope.

**Local validation so far:** PR #15 passed 32/32 regression checks; on real Sempra/SentinelOne queries both roots were suppressed from endorsed outputs but exploratory candidates preserved. PR #16's locally executed *99-query deliberately stratified* before/after study showed 34→24 automatic approvals and 37→47 reviews, with all ten lost auto approvals among shortened names; seed sets and leading exploratory candidates unchanged. No independent accuracy labels, and these changes remain in unmerged stacked PRs.

**Next MVP step:** implement a small, versioned tenant-scoped customer assertion and review-decision contract with provenance, acceptance authority, auditability and ASM permission separation. Begin CLI/JSONL or SQLite; avoid constructing a large policy UI. The GLEIF exact-name rule remains conservative until additional evidence can be incorporated under explicit policy. Continue inspecting exact-name review cases and evaluating alias/LEI vintage discrepancies.

## Purpose

**Primary product definition (2026-11-15):** Given a company name, Corporate Helix aims to discover as comprehensively as practicable **all mergers, acquisitions, and related corporate transactions associated with that company**, including historical transactions and relevant acquired/merged legal entities. It resolves identities, corroborates transaction evidence, preserves event dates/status, and recursively investigates additional leads. The principal deliverable is an **evidence-backed M&A inventory** containing counterparties, canonical names and aliases, identifiers, relationship/event type, dates, confidence/review status, and provenance. “All” is a coverage objective, **not a guarantee of exhaustive discovery**.

**ASM boundary:** Helix is **not** responsible for discovering the target company's network footprint. Its M&A findings provide additional company identities and qualified domain/hostname *discovery leads* for a downstream Attack Surface Management (ASM) platform. The ASM platform or customer system performs infrastructure discovery and decides which discovered hostnames/assets are added to scope. A transaction, acquired-company name, or historical ownership edge is **not itself proof of present-day asset ownership** and must not be silently promoted to an approved ASM seed.

**Secondary capabilities:** Corporate ownership graphs, broad corporate-family mapping, infrastructure attribution, virtual analysts, dashboards, and non-security applications are optional capabilities that leverage the core M&A dataset. Entity resolution, relationship modeling, evidence adjudication, temporal semantics, and evaluation are necessary *supporting foundations*, not competing primary product goals. A discovered lead is **not** automatically a verified transaction.

## Product success criteria

1. **M&A discovery recall:** independently measure known relevant transactions discovered for the input company, including historical and private-company cases where sources permit.
2. **Evidence quality:** track verified findings, investigatory leads, incorrect counterparties, and false-positive rates separately; distinguish signing/announcement from closing and divestiture.
3. **Actionable handoff:** output deduplicated corporate identities, aliases, dates, relationship context, evidence, and review state suitable for downstream ASM enrichment—not fabricated hostnames.
4. **Coverage transparency:** report which sources, filing periods, transaction types, and jurisdictions were checked or missing; never claim complete coverage without support.
5. **Secondary features must not displace core M&A discovery** unless explicitly reprioritized.

## Current engineering strategy: SEC EDGAR + GLEIF reliability

**Primary near-term investment:** Make the two foundational data sources as reliable and measurable as possible before expanding optional graph, dashboard, or standalone infrastructure features.

- **SEC EDGAR — unstructured transaction evidence:** Relevant M&A facts appear in different filing families, exhibits, sections, tables, and legal prose. Treat **retrieval/coverage** (did we fetch the relevant document?) separately from **extraction** (did we correctly find and interpret the transaction?). Maintain a filing coverage manifest, independently verified transaction gold sets, parser-miss taxonomy, and frozen regression cohorts. Selectively expand form/exhibit retrieval based on measured incremental yield, not indiscriminate fetching.
- **GLEIF — structured identity and ownership evidence:** Level 1 legal-entity records and Level 2 relationship records provide structured anchors for entity resolution, parent/child traversal, and candidate discovery. Validate indexing, identifier linkage, endpoint completeness, relationship semantics and dates, CLI integration, and reproducible results. **GLEIF relationship edges are not automatically M&A events** and cannot independently establish a transaction closing or historical acquisition.
- **Shared evidence/discovery pipeline:** Resolve the requested company; gather EDGAR events and GLEIF relationships; normalize/deduplicate entities; cross-reference sources; preserve event-versus-ownership distinctions, provenance, dates, uncertainty, and source gaps; recursively pursue trusted or reviewable leads without promoting guesses into facts.
- **Priority rule:** Prefer tasks that demonstrably improve EDGAR/GLEIF coverage, extraction correctness, structured-relationship correctness, integration reliability, or independently measured M&A recall/precision. Treat broad graph presentation, additional provider families, dashboards, and infrastructure scanning as secondary unless needed to validate the core.
- **Measurement rule:** Record retrieval coverage, extraction recall on retrieved evidence, entity/relationship accuracy, and end-to-end transaction recall separately. Never use an unverified candidate count as a discovery-accuracy metric.

This strategy explains the historical sequence: SEC legal documents proved difficult because both the location and structure of disclosures varied, so engineering focus shifted toward GLEIF's structured records while retaining EDGAR as an essential complementary source.

## Start here: current position

- The 30-company identity benchmark executed **30/30** cases with **zero execution errors**.
- Resolver outcomes in that run: **5 AUTO_RESOLVED, 24 REVIEW_REQUIRED, 1 NO_MATCH**.
- **0 cases scored for correctness**: independent ground-truth labels remain pending. These counts measure workflow behavior, **not accuracy**.
- **Sempra Energy** was matched to **SEMPRA ENERGY TRADING LLC**, and ownership traversal proposed **NATWEST GROUP PLC** as a REVIEW_REQUIRED root. This is an unsupported/incorrect proposed root for the intended Sempra query, **not** an AUTO_RESOLVED error. It is the first named regression case.
- Other suspicious root proposals, including SentinelOne, need verification before labeling as confirmed failures.
- The configurable identity-resolution milestone is queued in [BACKLOG.md](BACKLOG.md). **Planning is complete; implementation of this milestone is not yet claimed complete.**

## Current objective and design principles

Build a reliable identity-resolution layer that can distinguish **(a) who the queried company is**, **(b) which legal entities are connected**, and **(c) whether those connections represent current ownership, historical ownership, or M&A events**.

1. **Configurable by default:** Evidence weights, penalties, decision thresholds, and operating profiles (conservative, balanced, exploratory) live in version-controlled configuration, not scattered hardcoded values.
2. **Minimal hard safeguards:** Ownership-path validity alone never proves that the path's seed entity is the requested company. Unresolved identity/root conflicts cannot be promoted to verified automatic resolutions.
3. **Preserve discovery:** Retain uncertain leads and their evidence for review; do not silently discard them or misrepresent them as verified.
4. **Explain every decision:** Report signal contributions, source provenance, penalties, safeguard outcomes, decision reason, and configuration version.
5. **Measure accuracy honestly:** Independently verified ground truth is required before reporting precision, recall, or accuracy. Track incorrect proposed roots separately from incorrect automatic resolutions.

## Next execution plan (in order)

### Immediate milestone — priorities 1–4

- [ ] **1. Sempra regression test.** Query `Sempra Energy` must not yield NatWest as a verified root merely because `SEMPRA ENERGY TRADING LLC` has an ownership path to it. Preserve the investigatory candidate and evidence. Assert both candidate ranking/proposed-root quality and final decision status.
- [ ] **2. Configurable scoring engine.** Add validated, versioned scoring configuration with conservative/balanced/exploratory profiles and explicit decision thresholds. Treat initial numeric weights as uncalibrated hypotheses.
- [ ] **3. Identity integrity safeguards.** Keep a small set of explicit, non-bypassable checks, including independent seed-identity support before automatic ownership-based resolution.
- [ ] **4. Explainable resolution.** Return an auditable score breakdown and clear reasons for AUTO_RESOLVED, REVIEW_REQUIRED, and NO_MATCH.

### Validation and MVP integration — priorities 5–10

- [ ] **5.** Independently label the existing 30 benchmark cases.
- [ ] **6.** Run the same benchmark across the three profiles and compare outcomes and verified quality.
- [ ] **7.** Investigate Sempra, SentinelOne, and other suspect matches; promote verified failures into regression tests.
- [ ] **8.** Distinguish current, former, acquired, and divested ownership with temporal evidence.
- [ ] **9.** Feed verified identity and qualified M&A relationships into downstream corporate/ASM discovery.
- [ ] **10.** Evaluate the end-to-end MVP from evidence retrieval through actionable output.

**First-batch done when:** Sempra cannot become a verified NatWest root; existing resolver tests pass; profile changes affect scoring/thresholds without bypassing safeguards; decisions are reproducible and explainable.

## Existing project work and supporting records

- **GLEIF identity:** Level 1 and Level 2 data and an identity/root resolver are under development; legacy database migration and lookup-key changes were part of the preceding work. Verify the active branch and local DB paths before changing code.
- **SEC EDGAR/M&A discovery:** Coverage-manifest work and a 12-company cohort study are documented in [BACKLOG.md](BACKLOG.md). The backlog also records filing/extraction gaps and frozen-baseline cautions.
- **Prior studies:** Sony corporate expansion, M&A saturation, and company-specific EDGAR investigations have informed the discovery approach. Treat older run outputs as historical snapshots, not current verified performance.
- **Architecture decisions:** Consult the repository's `DECISIONS_*.md` / ADR documents for formal decisions. This file summarizes the present direction rather than superseding them.

## Where information belongs

| File | Purpose |
| --- | --- |
| **`docs/PROJECT_STATUS.md` (this file)** | Single entry point: goals, present state, immediate plan, session handoff |
| **`docs/BACKLOG.md`** | Full prioritized/parked queue, triggers, detailed findings, acceptance criteria |
| **`DECISIONS_*.md` / ADRs** | Durable architectural decisions and rationale |
| **Tests and evaluation results** | Reproducible evidence of behavior; source of truth for pass/fail and metrics |

Avoid copying detailed implementation notes into multiple documents. Link to the canonical source and update the summary here.

## Session handoff checklist

At the **start** of a session:
1. Read this file, then the relevant section of `docs/BACKLOG.md`.
2. Check the active Git branch, recent commits, open PRs, and test status. Do not assume unmerged work is on `main`.
3. Identify the next unchecked item and confirm its acceptance criteria.

At the **end** of a session:
1. Record what actually changed (paths, branch, commit/PR, tests run, results).
2. Update the checklist and any newly discovered blockers here.
3. Add detailed work or parked ideas to `docs/BACKLOG.md`; formal architectural decisions go to ADRs.
4. Write a one-paragraph **next-session starting point** below.

## Latest handoff

**2026-11-15:** Created this consolidated project-status entry point. The immediate next task is to inspect the current identity resolver and benchmark fixtures, then implement a failing Sempra regression test **before** modifying scoring. The configurable scoring framework follows, with no premature claims of benchmark accuracy. No code implementation or new test execution is asserted by this documentation update.

## Documentation consolidation

A first-pass repository documentation audit is recorded in [DOCUMENTATION_AUDIT.md](DOCUMENTATION_AUDIT.md). It indexes historical context/roadmap snapshots, decision logs, trust-boundary pitfalls, conflicting source-of-truth labels, and the remaining verification work. **This file remains the current session entry point;** historical handoff documents are retained, not deleted. The audit is not yet exhaustive, and older milestone completion claims require code/test verification before being promoted into current status.
