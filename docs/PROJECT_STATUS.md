# Corporate Helix — Project status and session handoff

**Last reviewed:** 2026-11-15  
**Current phase:** Identity-resolution quality and configurable evidence scoring  
**Next work item:** Sempra Energy regression test  
**Status convention:** This is a planning/handoff snapshot, not a claim that unverified local work or branches are merged.

## Purpose

Corporate Helix discovers and verifies corporate legal entities, ownership structures, and mergers/acquisitions. The intended MVP produces evidence-backed relationships that can inform Attack Surface Management (ASM) and other business functions. A discovered lead is **not** automatically a verified corporate relationship.

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
