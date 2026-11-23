# ADR: Customer evidence, organization-scoped trust policies, and safe authorization

**Status:** Accepted as a foundational product and data-model decision; implementation phased
**Date:** 2026-11-23
**Project:** Corporate Helix
**Scope:** Legal identity, ownership, M&A event evidence, analyst decisions, tenant policy, and ASM handoff

## Context

Helix's GLEIF baseline is intentionally conservative. The 99-query stratified resolver comparison showed 34→24 automatic resolutions and 37→47 review-required decisions under the exact canonical-name gate, with **no seed-set or leading exploratory-candidate changes**. All 10 automatic-to-review transitions occurred among shortened-name queries. That is an observation of decision behavior, **not independently verified accuracy**.

GLEIF is only one provider. Additional public, commercial, and customer-held sources will contribute more evidence. A customer may possess authoritative internal entity lists, transactions, or corporate records that cannot be publicly corroborated. Different customers have different authority structures, risk tolerances, data-sharing restrictions, and workflow goals. A single universal confidence threshold or a permanent GLEIF-only exact-name rule is not the product architecture.

## Decision — non-negotiable design contract

**Evidence is not a decision, and a decision is not an authorization.** Helix must support evidence from providers **and users**, while preserving its source, claims, history, policy context and permission boundaries.

1. **Customer-supplied data is first-class, not second-class.** Accept explicit user claims and attached internal documents, source-specific corroboration and feedback/corrections as *evidence records*. Provenance includes tenant, submitting principal, assertion or observation time, effective dates, reference to attachment/document if applicable, and raw claim. Do not quietly rewrite conflicting evidence to fit the current graph.

2. **Keep separate, typed dimensions:**
   - **Claim/evidence:** source assertions about exact subject, predicate, object, validity interval, and source ID; e.g., `COMPANY_A ACQUIRED COMPANY_B` as opposed to `COMPANY_A CONSOLIDATES COMPANY_B`.
   - **Source & authority:** public filing vs regulator/registry vs commercial vendor vs tenant's approved internal source vs self-reported analyst claim, each with declared role/scope.
   - **Confidence:** estimate or self-reported confidence **with calibration/source**, not a universal guarantee.
   - **Verification:** `UNVERIFIED`, `CUSTOMER_ASSERTED`, `CORROBORATED`, `INDEPENDENTLY_VERIFIED`, `CONFLICTED` (labels reflect their evidence rules; do not equate customer approval with independent verification).
   - **Disposition:** `ACCEPTED`, `REVIEW_REQUIRED`, `REJECTED`, with independent reason, reviewer and timestamps.
   - **Permitted use:** `INTERNAL_INVENTORY`, `INVESTIGATION_LEAD`, `ASM_DISCOVERY_SEED`, `ASM_SCOPE_APPROVED` are distinct permissions; **identity/transaction acceptance must never silently grant scanning or scope authority**.

3. **Per-organization versioned policy.** Tenants define which **authorized** user roles/sources can assert, confirm, or reject identity and relationship claims; whether their own accepted records count as sufficient for their own inventory; corroboration thresholds and conflict treatment; review gates; and permitted destinations. Start with conservative defaults. Users can choose *accept as customer-asserted*, *retain for review*, or *require corroboration*, with default review and explicit acceptance as a tracked event. Caller-entered confidence alone is **never** authority and never bypasses hard identity or authorization rules.

4. **Non-bypassable trust boundaries.** No customer-provided statement becomes universally or independently verified by fiat. No GLEIF accounting-consolidation relationship automatically becomes a dated M&A acquisition. No old or partial legal-name match becomes verified identity without sufficient evidence. No organization can accidentally accept another tenant's private assertion. No automated ASM authorization based merely on an accepted identity or acquisition. Authorized tenant administrators may use internal assertions to approve tenant-scoped internal outcomes, not global public truth or other customers' scope.

5. **Evidence and decision history must be append-only/auditable.** Record policy ID/version and decision engine version, evidence IDs, inputs, timestamps, reviewer/approver identity, reason, conflicts, and superseding decision. Corrections produce new events and reevaluation, not silent overwrite; raw source records remain intact. Implement reproducible decision replay for audits and experiments.

6. **Reevaluation is a normal workflow.** Additional SEC, GLEIF, registry, customer data, new dates, or policy revisions may move `REVIEW_REQUIRED` to `ACCEPTED`, or downgrade/revoke an earlier acceptance. Dependency relationships make affected decisions discoverable for reevaluation, but no unconditional automatic re-scoping.

7. **Separate cross-tenant learnings from private facts.** Tenant documents, claims, approvals, source permissions, and evidence IDs must not leak across tenant boundaries. Sharing, training, and cross-tenant propagation require explicit organizational controls and appropriate rights.

## Minimal conceptual record boundaries (not a mandated schema migration)

```text
EvidenceRecord
  id, tenant_id?, source_type, source_id, document_ref?, submitted_by?,
  observed_at, event_at?, effective_from?, effective_to?, raw_claim,
  subject_identifier, predicate, object_identifier, provenance

EvidenceAssessment
  claim_id, evidence_ids[], verification_status, conflicts[], confidence?,
  confidence_basis?, assessed_at, assessment_version

PolicyVersion
  tenant_id, policy_id, version, source_authority_rules,
  required_corroboration, conflict_rules, reviewer_roles, use_permissions

DecisionEvent
  tenant_id, claim_id, policy_id, policy_version, decision_engine_version,
  disposition, decision_reason, approved_by?, decided_at,
  evidence_ids[], permitted_uses[], supersedes_event_id?
```

`tenant_id = null` is only for properly rights-cleared provider evidence; absence of tenant ID must not itself imply public disclosure authorization.

## Concrete behavior examples

- Customer states `Acme Security LLC is our subsidiary`, and an authorized tenant reviewer chooses **Accept as customer-asserted**. The tenant's inventory may show it as accepted with *customer assertion* provenance. It is **not** independently verified and **not** automatically in active ASM scanning scope.
- Customer enters `Acme Security LLC acquired Company B` with 95% self-reported confidence but selects **Require corroboration**. The claim stays review-required until the tenant's policy is met; the numeric confidence cannot shortcut policy.
- GLEIF shows a consolidation path but the query matches a different legal entity. Preserve path as exploratory, do not endorse its parent as the requested company's root. SEC/company customer evidence can later anchor the identity and trigger reevaluation.
- One tenant accepts a private entity relationship while another rejects it. Both tenant decisions coexist; the shared public graph is not silently rewritten.

## Implementation sequence / MVP constraints

**P0 — immediately after identity gate validation:**
1. Keep this ADR linked from project status and backlog; do not spend the MVP cycle on a broad policy admin UI.
2. Define a tiny *append-only*, tenant-scoped customer assertion + review-decision contract (first pass can be JSONL/SQLite plus import CLI). Include tests for authorization, tenant isolation, provenance, confidence-vs-approval, conflicts, and downstream ASM permission.
3. Start with one conservative default policy and one explicit tenant-controlled acceptance path. Keep unimplemented statuses unclaimed and version the contract.
4. Adapt resolver outputs so evidence, exploratory candidates and endorsed identity remain separate; evaluate a frozen benchmark before/after adding approved customer evidence.

**P1 — as actual additional sources are integrated:** source adapters, independent corroboration, automatic reevaluation and broader configurable policy profiles.

**Later:** customer-facing policy controls/dashboard, richer role management, multi-tenant workflows and source reputation calibration.

## Evaluation / acceptance

- Same evidence with differing tenant policies yields separately auditable tenant-scoped decisions; another tenant's private assertion is never visible.
- A customer-approved claim can be `ACCEPTED` while `INDEPENDENTLY_VERIFIED=false` and `ASM_SCOPE_APPROVED=false`.
- User-selectable review does not discard evidence, and a subsequent corroboration event can be evaluated without re-ingesting or changing raw records.
- Conflict, expired relationship periods, revoked approval and policy version changes preserve the full decision history.
- Continue separately measuring identity resolution, acceptance rate/review burden, parent attribution correctness, and actual dated M&A recall with independent ground truth.

## Relationship to earlier work

This ADR **extends rather than replaces** PR #15's conservative *GLEIF-only* exact canonical name anchor and PR #16's before/after decision benchmark. The exact-name gate is a provisional source-limited safeguard. Later independent or authorized tenant evidence may justify acceptance under explicit policy without weakening minimum safeguards or relabeling unverified claims as global truth.
