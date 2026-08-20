# CONTEXT — Entity Graph Project

Paste this whole file into a new Claude chat to resume with full context.
Update it as you go — this is the source of truth, not the chat history.

## The pitch
Coming from BitDiscovery (acquired by Tenable) and 3 years running ASM at
Tenable. No competitor in that time had subsidiary/related-entity mapping
worth trusting. Target team is a new startup merging network + ASM — same
people who built BitDiscovery. Plan: bring them a working subsidiary
resolution pipeline that beats what BitSight/SecurityScorecard-style tools
surface, offered for a fee once they've got a few companies under their belt.

## What "good" looks like
Not just a company graph — a graph with:
1. Per-edge source attribution (which dataset asserted this relationship)
2. Per-edge confidence score based on *signal agreement*, not string score alone
3. A hook into ASM scope: resolved entities -> domain/ASN/IP ownership inference

Differentiator vs. competitors: auditable ("here's why we believe this is a
subsidiary") instead of a black-box score, and coverage of small/recent
subsidiaries that big vendor-risk platforms lag on.

## Data sources (decided)
- **GLEIF** — free, no key, LEI + Level 2 relationship records (who owns whom).
  Strongest structured signal when available. Cross-mapped to OpenCorporates IDs.
- **SEC EDGAR** — free, US public companies. Exhibit 21 (10-K) or subsidiary
  list within 20-F (foreign private issuers, e.g. Sony).
- **OpenCorporates** — free tier rate-limited; registry-level entities that
  never needed an LEI. Good for entity resolution baseline (name, jurisdiction,
  registration number) even without paid relationship data.
  CORRECTION (confirmed during Phase 0): OpenCorporates now requires an
  api_token for all requests — the old keyless free-search access is gone.
  Free tier still exists but needs registration at
  https://opencorporates.com/api_accounts/new. Set OPENCORPORATES_API_TOKEN
  env var before running fetch_opencorporates.py.
- **Companies House (UK)** — free API, good officer/PSC data.
- Not yet integrated: D&B, Bureau van Dijk/Orbis (paid, gold standard —
  candidate for later validation, not MVP).

## Entity resolution approach (decided)
1. **Legal-form normalization first**, before any similarity scoring. Use
   GLEIF's ISO 20275 Entity Legal Forms (ELF) code list as the base
   dictionary — don't hand-roll a suffix list. Output: canonical name +
   separate legal-form field (keep the form as metadata, don't discard it).
2. **Blocking** before pairwise comparison (first token / jurisdiction /
   industry code) — brute-force pairwise doesn't scale against full registry
   pulls.
3. **Similarity ensemble**: Jaro-Winkler (prefix-weighted, good for company
   names) + Levenshtein + a token-based method (Jaccard or Monge-Elkan) to
   catch reordered names like "International Business Machines" vs "Business
   Machines International."
4. **Structured-signal gate**: string similarity alone can't disambiguate
   identically-named unrelated entities in different jurisdictions. Gate/boost
   matches using registration number, jurisdiction, address, or an actual
   LEI ownership edge. False positives (pulling unrelated infra into ASM
   scope) are worse than false negatives here.
5. **Confidence = function of which signals agree**, not raw string score.
   LEI edge + 0.95 similarity should outrank 0.98 similarity with no
   structured corroboration.

## Test company
**SentinelOne** — Phase 0/1/2/3 development and validation target. Chosen
over Sony deliberately: smaller entity count (fully hand-verifiable ground
truth, not just a sample), direct personal institutional knowledge (former
employee), fewer jurisdictions/legal-form varieties so normalization logic
gets validated before Sony-level complexity hits it. Also a stronger demo
case for the pitch — "here's what we surface on a company I know cold."

**Sony** — held in reserve as the *final* stress test once the pipeline
works end-to-end on SentinelOne. Deliberately messy: many jurisdictions
(Japan, US, EU, APAC), JVs, a 2021 rename (Sony Corporation -> Sony Group
Corporation), wide legal-suffix diversity (K.K., G.K., GmbH, S.A., Pte. Ltd.).
Do not start Sony work until SentinelOne resolution is validated.

Ground truth: [not yet filled in — add known SentinelOne subsidiaries/related
entities you can personally verify, including a couple of deliberately tricky
cases (JVs, acquisitions, name changes) since those are the highest-value
rows for catching where competitor tools fail]

## Current phase
M1 — Corporate Attribution Resolver. EDGAR canonicalization, GLEIF Level 1/Level 2
JSON parsing, RDAP domain registration parsing, and conservative RDAP->GLEIF
candidate ranking are implemented. Next task is validating the GLEIF parser against
one of the user-downloaded real GLEIF snapshots, then joining a resolved LEI through
Level 2 ownership evidence and the existing SentinelOne EDGAR assertions.

OpenCorporates is now optional only because its acceptable-use/licensing constraints
may not fit the intended proprietary/commercial MVP. The architecture must not depend
on it.

## Parking lot (real rabbit holes, deliberately deferred)
- D&B / Orbis paid data integration — later, for validation only
- Multi-language name matching (Sony's Japanese-language entity names) — flag
  now, solve later; don't let this stall the ELF/normalization MVP
- Historical/point-in-time graph (tracking M&A over time, not just current
  state) — v2 concern
- Full ASN/certificate inference logic — RDAP/domain attribution has moved into M1; ASN and certificate expansion remain later

## How to resume a session
Run `make status` in the project root and paste the output (this file) into
chat. Then say what you're working on right now — don't re-explain the whole
project, just the current task.
