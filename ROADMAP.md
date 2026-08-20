# ROADMAP

One active task at a time. If something else comes up mid-task, it goes in
the parking lot in CONTEXT.md, not into this sprint. Rabbit holes are real —
the discipline is writing it down instead of chasing it.

## M1 — Corporate Attribution Resolver (ACTIVE)
- [x] Canonical entity / relationship / infrastructure evidence models
- [x] EDGAR adapter: existing SentinelOne Exhibit 21 output -> 29 unique entities / 28 deduped subsidiary assertions
- [x] GLEIF Level 1 JSON adapter
- [x] GLEIF Level 2 relationship JSON adapter
- [x] RDAP domain-registration adapter (saved JSON + live MVP lookup)
- [x] Conservative RDAP -> GLEIF candidate matcher using name + address + country signals
- [x] Unit test proving same-name structured conflict can reject a false candidate
- [ ] Run adapter against user-downloaded real GLEIF snapshot and fix any schema edge cases
- [ ] Run RDAP -> GLEIF mapping on a real domain with exposed registrant data
- [ ] Join resolved LEI to GLEIF Level 2 parent chain and EDGAR family assertions
- [ ] Produce first human-readable SentinelOne attribution report

## Phase 1 — Normalization (IN PROGRESS UNDER M1)
- [ ] Pull GLEIF ISO 20275 Entity Legal Forms (ELF) code list, build lookup table
- [ ] Write normalize.py: tokenize -> strip/tag legal form via ELF -> canonical
      name + legal_form field (keep both, don't discard)
- [ ] Handle punctuation/case/whitespace variants
- [ ] Test against Sony entity names (once fetched — see Phase 0 below)
- [ ] Unit tests covering: US suffixes, Japanese K.K./G.K., European GmbH/S.A.,
      informal abbreviations not in ELF (log these as gaps, don't block on them)

## Phase 0 — Data collection (prerequisite, do alongside Phase 1)
Target company: SentinelOne (Sony deferred to Phase 5a — see below)
- [x] Manually build ground truth set — done via user's raw EDGAR/OpenCorporates
      pull (DevTools scrape), cross-checked against user's personal knowledge.
      See tests/ground_truth_sentinelone.json (34 entities, cleaned/deduped,
      confidence-tagged, low-confidence rows flagged for follow-up: Stride
      Security, Observo AI, PinnacleOne, SentinelOne Consulting & Real Estate
      Agency (BC, Canada) — name looks off, needs verification)
- [~] GLEIF integration — local Level 1 + Level 2 dump parsers implemented; live/delta fetch/sync deliberately deferred until real snapshot validation
- [x] fetch_edgar.py — real implementation done. Finds CIK via SEC ticker
      lookup, locates EX-21 exhibit within recent 10-K filings via filing
      index JSON, extracts rows (HTML table if present, else line-split
      fallback). NOTE: Exhibit 21 has no standardized format across filers —
      extraction is best-effort, needs human sanity-check against ground
      truth, same as OpenCorporates. Also untested against live SEC
      (sec.gov not in sandbox's network allowlist) — user needs to run and
      compare output to tests/ground_truth_sentinelone.json.
- [x] fetch_opencorporates.py — real API implementation done (replaces
      DevTools scrape). NOTE: OpenCorporates now requires an api_token —
      no more keyless free access, this changed from what we assumed at
      project start. Untested against live API (not in sandbox's network
      allowlist) — user needs to run first real call and confirm it works.
- [ ] Diff fetcher output against ground truth once fetch_gleif/fetch_edgar
      are real (opencorporates already validated: zero false positives on
      the 4-state SentinelOne search, confirmed by user)

## Phase 2 — Blocking + similarity ensemble (NOT STARTED)
- [ ] Blocking strategy (first token / jurisdiction / industry code)
- [ ] Jaro-Winkler + Levenshtein + token-based (Jaccard/Monge-Elkan) scoring
- [ ] Weighting/combination logic across the three
- [ ] Benchmark against ground truth set

## Phase 3 — Structured-signal gating + confidence scoring (NOT STARTED)
- [ ] Gate string matches with registration number / jurisdiction / address
- [ ] Confidence score as function of signal agreement, not raw string score
- [ ] Output: canonical entity graph with per-edge source + confidence
- [ ] ACCEPTANCE TEST: gate must reject "SentinelOne Consulting & Real Estate
      Agency" (BC, Canada) — confirmed real-world false positive from
      OpenCorporates, high string similarity, no real relationship to
      SentinelOne the company. See tests/ground_truth_sentinelone.json.

## Phase 4 — ASM hookup (NOT STARTED)
- [~] Domain ownership inference (RDAP registrant org/address -> GLEIF candidate matching implemented; ownership-chain join pending)
- [ ] ASN ownership inference
- [ ] SSL cert org field cross-check
- [ ] Map resolved entity graph -> scan scope output

## Phase 5a — Sony stress test (NOT STARTED — final validation only)
Do not start until Phases 0-3 are validated end-to-end on SentinelOne.
- [ ] Run full pipeline against Sony (multi-jurisdiction, JVs, 2021 rename,
      wide legal-suffix diversity — the deliberately hard case)
- [ ] Build Sony ground truth set (smaller/sampled is fine here — this is
      a stress test, not a primary validation set)
- [ ] Note failure modes distinct from SentinelOne (e.g. non-Latin legal
      forms, JV ambiguity) — decide fix-now vs. parking-lot per issue

## Phase 5b — Demo prep (NOT STARTED)
- [ ] Package SentinelOne (+ Sony if ready) results into a demo-able
      comparison: what this pipeline surfaces vs. what a competitor tool
      would show
- [ ] Write up the auditability angle (per-edge "why we believe this")

## Phase 6 — Acquisition/dissolved-entity tracking (MILESTONE, not scoped yet)
Different animal from the subsidiary graph: current-state sources (GLEIF/
EDGAR/OpenCorporates) miss entities dissolved/absorbed post-acquisition,
but their domains/ASNs can persist unmonitored for years — likely blind
spot in competitor tools, worth building eventually. Needs point-in-time/
historical data, not live registry queries. Do not start until Phase 0-3
validated on SentinelOne. Full spec TBD when we get here.

---
Last updated: 2026-08-12 — M1 Corporate Attribution Resolver code slice implemented

### GLEIF validation update — 2026-08-12
- [x] Validate Level 1 parser against a real 9,203-record daily delta.
- [x] Preserve transliterated names and addresses.
- [x] Preserve registration status, validation status, creation/update/renewal dates.
- [x] Preserve LegalEntityEvents and successor LEIs/names.
- [x] Confirm daily delta includes explicit M&A/absorption/dissolution/liquidation event evidence.
- [ ] Build streaming/indexing bootstrap for the 12 GB full Level 1 Golden Copy.
- [ ] Parse the 1 GB RR Golden Copy and link child/parent LEIs into the local index.
- [ ] Add RDAP-to-index candidate lookup so matching does not scan the full GLEIF universe per request.
