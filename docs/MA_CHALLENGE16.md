# Unseen M&A challenge — 16 user-selected companies

**Study:** `MA_CHALLENGE16_V1`  
**Baseline rule:** Preserve original query strings and order. Do not tune per-company rules or declare false negatives until individual failure stages and evidence have been inspected.

This study directly addresses the risk that Helix misses a transaction **before** identifying useful source documents. The 16 queries in `data/eval_study/ma_challenge16_v1.json` were supplied by the user and are kept verbatim. They include large public acquisitive companies, private or potentially non-US businesses, a former acquired company (Monsanto), short names (Meta), and spelling/name variants (Exon Mobile, The Proctor and gamble Company, jp Morgan Chase). **Do not silently replace the query**: correcting a name is part of the quality analysis and should be tracked as a separate input variation in a later controlled run.

## Baseline finding and targeted correction (2026-11-24)

The user's first **local** 16-company execution at commit `fae3715` recorded **0 AUTO_RESOLVED, 12 REVIEW_REQUIRED, 4 NO_MATCH, 0 GLEIF runtime errors**. Test suite for the challenge subsequently passed **6/6** at `8d6d5e3`. This baseline JSON remains immutable and must not be confused with a rerun after fixes.

Inspecting source identified a **specific exact-name retrieval defect**: `build_gleif_lei_index.py` stores `legal_name_normalized = legal_name.casefold()` (punctuation retained), while `find_seed_matches` queried only the punctuation-stripped `normalize_name(query)`; for `Johnson & Johnson`, that produces `johnson johnson` and fails to retrieve the indexed exact name `johnson & johnson`. GLEIF graph traversal later reached the correct Johnson & Johnson legal entity as an *exploratory* parent but could not anchor it from canonical seed discovery.

A deliberately narrow resolver fix checks both the raw case-folded query and query-normalized form against the legacy index, then requires full normalized-name equality **in Python**. New synthetic tests verify canonical recovery, continued caution for partial/ambiguous identities, and no automatic endorsement from graph parents. This preserves the original GLEIF dataset and conservative policy. More general punctuation/Unicode/alias mismatches and SQL search caps remain separately open.

After pulling the patch, run:

```bash
python3 -m unittest discover -s tests -p 'test_canonical_punctuation_anchor.py' -v
python3 -m unittest discover -s tests -p 'test_ma_challenge16.py' -v
python3 code/eval/run_ma_challenge16.py --mode local \
  --out data/eval_study/ma_challenge16_local_after_punctuation_v1.json
```

Compare original and after report, especially Johnson & Johnson, without overwriting the frozen baseline. An improvement in identity decision does **not** establish any newly discovered M&A transactions; live SEC stage validation follows independently.

## 1. First run: fast local identity/alias coverage — no SEC requests

```bash
git fetch origin
git switch eval/ma-sixteen-company-challenge
python3 -m unittest discover -s tests -p 'test_ma_challenge16.py' -v

python3 code/eval/run_ma_challenge16.py \
  --mode local \
  --out data/eval_study/ma_challenge16_local_v1.json
```

This evaluates the 16 submitted names against the existing canonical LEI, Level 2, and independently verified compact GLEIF alias indexes. It reports exact/partial/alias matches, review and endorsed root status, candidate count, and **errors**. GLEIF accounting consolidation is **not** an M&A acquisition database; absent results mean identity discovery is incomplete, not absent historical acquisitions.

## 2. Second run: source retrieval and transaction extraction (networked)

SEC requires a genuine contact user-agent. This uses the existing EDGAR CIK resolver, production `fetch_ma_filings`, `EdgarMAExpansionProvider`, GLEIF fallback provider, and the existing iterative expansion engine without relaxing evidence/pivot trust gates.

**Begin with a small run to establish live dependencies and fetch behavior**:

```bash
python3 code/eval/run_ma_challenge16.py \
  --mode live \
  --only johnson_and_johnson \
  --only walmart \
  --user-agent "Your Research Name your-real-email@domain.com" \
  --out data/eval_study/ma_challenge16_live_initial_v1.json
```

Replace the example user-agent with a genuine SEC-compliant name and email. Live retrieval may take substantial time, particularly for prolific SEC filers, because the **existing production retriever has no per-company document cap**. It downloads eligible filings and extracts relevant sections. The runner uses one ticker directory request for the run, but cannot guarantee availability, rate-limit freedom, or processing time. It records provider errors rather than silently declaring no findings. If the initial run performs acceptably, run all 16 using a different `--out` file and omit `--only`:

```bash
python3 code/eval/run_ma_challenge16.py \
  --mode live \
  --user-agent "Your Research Name your-real-email@domain.com" \
  --out data/eval_study/ma_challenge16_live_all_v1.json
```

**Important SEC limitation:** the production name-to-CIK resolver searches `company_tickers.json` by normalized exact registrant name. This is **not a complete directory of SEC registrants**, excludes many private companies, and can miss filings under different legal names, predecessors, or subsidiaries. `NO_EXACT_TICKER_NAME_MATCH` means **CIK not established by that lookup**, not that the company has no CIK or no acquisitions. The first live failure layer we expect to characterize is likely SEC lookup itself.

## Interpret the stage results

Each case records:

| Output | Meaning |
|---|---|
| `gleif_identity` | Canonical/alias seed and conservative identity/root status; review candidates retained |
| `sec_directory` | Ticker directory exact-name lookup; separate matched, no exact match, and network error |
| `ma_pipeline.sec_retrieval` | Whether SEC filing fetch was even attempted |
| `filings_with_selected_sections` | Count of SEC filings selected by production parser; **not** total available filings |
| `selected_sections` | Relevant extracted text regions, only within successfully selected documents |
| `review_candidate_entities` | Distinct parser-produced M&A leads; these are not verified transactions |
| `ma_evidence_events` | Parsed event evidence with provenance, form, accession, event type, parties |
| `provider_errors` and `state` | Explicit runtime/source failures; review separately |
| `quality: NOT_SCORED` | No independent M&A truth labels, so **no recall or precision claim** |

A zero candidate count is not proof of failure unless an independently established transaction is known, relevant, and in scope. A retrieval error is not a successful negative result. Private-to-private acquisitions, ownership structures, and historical corporate events may never be fully represented by public SEC filings.

### Next diagnostic gate after obtaining results

1. Classify every case that stopped at name/CIK resolution, corpus retrieval, section selection, entity recognition, event parsing, or evidence/pivot eligibility. Don't classify a later stage as a failure if the earlier stage was never reached.
2. Gather a small **independently verified transaction gold set** (at least one dated acquisition/merger/divestiture per company where verified records exist, and note source/period limitations); do not invent it from parser output.
3. For known missed events, inspect the relevant document via existing `code/eval/explain_miss.py` and coverage manifest. Fix *reusable failure mechanisms*, not company-specific shortcuts.
4. Keep this challenge cohort frozen for regression runs as changes land.

This PR is **a measurement harness, not a new M&A discovery provider**. We intentionally do not merge source, identity, SEC, or parser changes into the benchmark before observing baseline behavior.
