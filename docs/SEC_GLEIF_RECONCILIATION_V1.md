# SEC–GLEIF relationship reconciliation V1

Status: **READ-ONLY DIAGNOSTIC IMPLEMENTED — cross-source transaction reconciliation not implemented**  
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

## First slice implemented (2026-11-26)

- `code/eval/compare_sec_gleif_coverage.py` reads the frozen SEC S1 event JSONs and gold set, calls `resolve_company_root` on the seed and each counterparty at **both** the event date and a current comparison date, and writes a new JSON report exclusively (never overwrites).
- Explicitly keeps SEC CIK and GLEIF LEI identities separate. Both GLEIF root and exact-name seed LEIs are shown without equating a root with the queried company. No SEC network calls; no fact promotion, graph mutation, or ASM scope decisions.
- GLEIF results are status-distinguished: `AUTO_RESOLVED`, `REVIEW_REQUIRED`, `NO_MATCH`, `INSUFFICIENT_EVIDENCE`, and `ERROR`. An absent SEC result is `NOT_CHECKED`, not a scored miss. Event-date queries carry the warning that a modern GLEIF snapshot is **not** a historical reconstruction.
- `tests/test_sec_gleif_coverage.py` adds four isolated tests, including Monsanto-shaped SEC candidate-only miss and separate historical/current GLEIF views.
- Tests and live local GLEIF comparison **not yet executed**; run on the user's Mac with installed databases, after pulling branch.

```bash
git pull --ff-only
python3 -m unittest discover -s tests -p 'test_sec_gleif_coverage.py' -v
python3 code/eval/compare_sec_gleif_coverage.py \
  --study data/eval_study/ma_recall_four_v1.json \
  --results data/eval_study/ma_recall_four_results \
  --gold-dir data/eval_gold/ma_recall_four \
  --lei-index data/processed/gleif_lei.sqlite \
  --rr-index data/processed/gleif_rr.sqlite \
  --as-of 2026-11-26 \
  --out data/eval_study/sec_gleif_coverage_v1.json
```

Upload the resulting report so we can see what GLEIF actually contributes. Do not use this comparator to claim an increase in historical M&A recall or to assert exact parent relationships: that is a later, explicitly separate step requiring period-level L2 evidence and reconciled identifiers.

## Live four-company diagnostic findings and raw L2 next step

User ran `compare_sec_gleif_coverage.py` successfully on 2026-11-26; report `data/eval_study/sec_gleif_coverage_v1.json` reviewed. The exact legal-entity and proposed parent LEIs:

| Pair | Exact seed LEI | Exact counterparty LEI | Current graph proposal |
| --- | --- | --- | --- |
| Monsanto → Bayer | `NONUZEX43GHIPSVDD938` | `549300J4U55H3WP1XT59` | Bayer 1 direct + 1 ultimate parent votes; root still REVIEW_REQUIRED |
| Abiomed → Johnson & Johnson | `5493001EZN4ZTB4Z5887` | `549300G0CFPGEF6X2043` | J&J 1 ultimate-parent vote; root still REVIEW_REQUIRED |
| GE / Alstom Power and Grid businesses | GE `3C7474T6CDKPR9K6YT90` | no exact LEI | Business-unit label not a GLEIF legal name |
| Walmart / VIZIO Holding Corp. | Walmart `Y87794H0US1R65VBXU25` | no exact LEI | No GLEIF legal-name match |

The parent votes are topology evidence, **not** proof of a historical transaction or accepted current root. Particularly important: Monsanto as-of 2018-06-07 did NOT project a Bayer parent while current-as-of does; modern GLEIF relationship status applied to a historic date is not a reconstructed past snapshot.

### Raw L2 pair-level audit (implemented, verification pending)

`code/eval/inspect_gleif_l2_edges.py` reads the saved coverage JSON and exact LEIs for **both entities**. It opens the local L2 database read-only, emits raw matching direct/ultimate accounting-consolidation rows in either direction, and marks row eligibility on 2026-11-26 versus the sentinel event date. It emits neither an M&A event nor attribution authorization. `tests/test_inspect_gleif_l2_edges.py` adds four offline checks.

```bash
git pull --ff-only
python3 -m unittest discover -s tests -p 'test_inspect_gleif_l2_edges.py' -v
python3 code/eval/inspect_gleif_l2_edges.py \
  --coverage data/eval_study/sec_gleif_coverage_v1.json \
  --rr-index data/processed/gleif_rr.sqlite \
  --out data/eval_study/sec_gleif_l2_pairs_v1.json
```

Review `sec_gleif_l2_pairs_v1.json` for raw relationship period/status/source information before proposing cross-source promotion. Known L2 period-flattening and snapshot-freshness defects remain an explicit risk. If a relationship row is absent or only expired, do not automatically claim a verified historical acquisition.

## Production integration slice: shared review-only graph (2026-11-27)

**Implemented; live execution and local tests pending** on `eval/ma-recall-four-baseline`:

- `providers/gleif_relationship_provider.py` uses a unique exact canonical L1 name anchor (not a proposed ultimate-root identity) or an explicit LEI to fetch raw L2 accounting parent and child edges, preserving the original child LEI, parent LEI, relationship type, status, effective dates, accounting dates, source file, validation, initial registration, last update and snapshot eligibility. The return facts have `fact_type=CORPORATE_RELATIONSHIP`, `status=REVIEW` and `pivot_eligible=False`. Fanout is capped and truncation reported. Inactive/dated edges are evidence-only and cannot become historical acquisitions.
- `ma_cross_source.py` uses the existing trusted iterative-expansion engine with EDGAR and the GLEIF relationship provider together. After trusted iterations, it enriches SEC `REVIEW` counterparty candidates without pivoting or recursively exploring them. It links an EDGAR candidate to a GLEIF edge **only if both the filing pivot and counterparty have separately anchored exact LEIs and the L2 edge contains precisely that pair**. Such links are tagged `REVIEW_ONLY_NOT_TRANSACTION_CORROBORATION`. No SEC syntax changes.
- `run_company_ma_expansion.py` now routes the production command through that integration, outputs complete facts + `cross_source` coverage under `--json`, accepts `--cik` and `--sec-user-agent` (or `SEC_USER_AGENT` environment variable). A CIK is never interpreted as an LEI.
- `tests/test_ma_cross_source_integration.py` includes independent source discovery, candidate/evidence association, missing counterparties, typed identity, and historical effective-date safeguards.

### Verify locally

```bash
git pull --ff-only
python3 -m unittest discover -s tests -p 'test_ma_cross_source_integration.py' -v
python3 code/run_company_ma_expansion.py \
  --company 'Monsanto Company' \
  --cik 0001110783 \
  --max-iterations 1 \
  --max-gleif-edges 50 \
  --max-sec-candidates 25 \
  --as-of 2026-11-26 \
  --json > data/eval_study/monsanto_integrated_v1.json
```

The last command can contact SEC EDGAR live; supply a legitimate `SEC_USER_AGENT` before running. It also uses existing local GLEIF SQLite files. If SEC returns no filings, the L2 provider may still emit evidence. The report is NOT a new event-recall score.

**Still pending**: local test verification and live output inspection; historical GLEIF source period-flattening repair; full typed CIK–LEI crosswalk persisted outside fact metadata; differentiated direct/ultimate relationship time history; evidence-driven transaction lead generation beyond explicitly matched SEC counterparties. In particular, independent L2 rows alone are not M&A claims, even when the direct and ultimate parent LEIs agree.

## Bidirectional research slice (2026-11-27)

`code/ma_bidirectional.py` adds bounded GLEIF-to-SEC research *probes*.
The integrated CLI now accepts `--gleif-sec-probes N` (default **0** to avoid unexpected EDGAR network traffic or fanout).

- Group direct and ultimate accounting relationships by exact counterparty LEI. Each unique LEI becomes at most one SEC probe, even if two L2 records exist.
- Only evidence facts anchored to the current research seed and with non-invalid relationship periods become leads. Prefer legal entities consolidated by the seed; display how many leads were deferred by the configured probe budget. Probe order is deterministic, **not** a confidence-ranked transaction prediction.
- A probe is a temporary, nonpivot `LEGAL_ENTITY` fact fed to the *existing* SEC extractor, not a trusted recursive expansion. No SEC parser modifications and no automatic company trust/pivot or ASM attribution.
- An event counts as a provisional pair match only when the SEC extractor identifies the exact original seed as the counterparty, with an M&A-class event type and a matching filing-pivot identity. No SEC result is **not proof** of no transaction, particularly for private firms.
- Return a separate `gleif_to_sec_research` report in the CLI JSON. Both the positive and negative outcomes are explicitly research-only; no event date is synthesized from GLEIF effective/start/accounting dates.
- `tests/test_ma_bidirectional.py` covers pair matching, wrong counterparty, wrong filing pivot, missing SEC data, event-type gate, max-probe budget/deduplication and disabled default.

Verification (requires user's local GLEIF SQLite and optional live EDGAR network; set `SEC_USER_AGENT` to a real identifying value):

```bash
git pull --ff-only
python3 -m unittest discover -s tests -p 'test_ma_bidirectional.py' -v
python3 -m unittest discover -s tests -p 'test_ma_cross_source_integration.py' -v

python3 code/run_company_ma_expansion.py \
  --company "Bayer Aktiengesellschaft" \
  --max-iterations 1 \
  --max-gleif-edges 30 \
  --gleif-sec-probes 2 \
  --as-of 2026-11-26 \
  --json > data/eval_study/bayer_reverse_discovery_v1.json
```

**Limitations:** This first bounded probe does not yet use a typed SEC CIK–LEI index, so historical/delisted companies can lack CIK lookup and produce an empty SEC response. It doesn't fix the known period flattening in the GLEIF importer. `AGREED_TO_ACQUIRE` with a parser-emitted `COMPLETED` status needs separate stage-consistency handling; a pair match alone is not transaction confirmation. For large parent companies, the first N leads are determined by alphabetical order after direction and publication status, not by likely M&A relevance. The earlier graph still fetches the first capped L2 rows, which can bias coverage; improvement to evidence-aware/fair pagination is a subsequent step.

## Reverse SEC coverage diagnostics and lead ordering (2026-11-27)

The Bayer reverse run (30 L2 rows, 15 distinct companies, 2 attempted probes) showed that the old `NO_SEC_PAIR_EVENT_FOUND_NOT_NEGATIVE_PROOF` outcome conflated missing CIK, no selected filings and actual parser search. The CLI now captures on each probe:

- `sec_probe.status`: `NO_SEC_IDENTITY`, `NO_SEC_FILINGS`, `NO_SEC_SECTIONS`, `FILINGS_RETRIEVED`, or `CIK_RESOLVED_FETCH_PENDING` if fetching throws; `UNKNOWN_PROVIDER_COVERAGE` for injected providers that do not provide telemetry.
- `sec_probe.cik`, `identity_method`, `filings_retrieved`, and `sections_retrieved`; the last field counts selected SEC filing sections/locator regions, **not** successful extraction or all EDGAR submissions.
- `decision`: `NO_SEC_IDENTITY`, `NO_SEC_FILINGS_RETRIEVED`, `NO_SEC_SECTIONS_RETRIEVED`, `SEC_FILINGS_EXAMINED_NO_PAIR_EVENT`, `NO_SEC_PAIR_EVENT_FOUND_COVERAGE_UNKNOWN`, `SEC_TRANSACTION_CANDIDATE_FOUND_REVIEW`, or `SEC_PROBE_ERROR`.
- `research_priority` and `priority_basis` now sort deterministic candidates by seed-as-parent, current eligibility where available, PUBLISHED registration, **newer relationship period start**, then legal name. Date ordering is a research heuristic only; it does **not** assert when an acquisition happened.

The current CIK name resolver still primarily searches SEC's tickers index; it is not sufficient for private, delisted or many foreign issuers. A CIK lookup miss is now observable rather than silently reported as zero transaction events. The old alphabetical selection behavior is superseded; results from the same `--max-gleif-edges` cap can still be unrepresentative because the L2 query first sorts by child LEI. The GLEIF historical period importer remains a separate unresolved correctness task.

Targeted tests extended in `tests/test_ma_bidirectional.py`. Verify on local Mac, then repeat the Bayer command with the same options to compare the new stage-specific outcomes. A real `SEC_USER_AGENT` is needed for reliable live EDGAR access.

## SEC identity crosswalk and parent-side filing evidence (2026-11-27)

The Bayer v2 run proved that zero filings were examined: both selected GLEIF subsidiaries were `NO_SEC_IDENTITY`, as was the Bayer parent seed. We now add two **conservative** capabilities:

1. `code/sec_identity_bridge.py` supports an **optional audited CSV**, selected with `--sec-cik-crosswalk PATH`. Required columns: `lei,cik,verification_status,evidence_url`. An exact LEI is used to retrieve a CIK only if `verification_status=VERIFIED`, its evidence URL is present and HTTP(S), the CIK parses to 1–10 digits, and no row for that LEI presents a conflicting valid CIK. The URL is a cited claim supplied by a curator; **the loader does not independently verify URL content**. Ambiguous LEI mappings resolve to no CIK. All source and resolution-method fields are preserved in `sec_probe`. Without an audited entry, existing exact-name SEC ticker matching is still permitted **as a research candidate**, never as verified LEI–CIK equivalence. No fuzzy LEI–CIK joins are performed.
2. `code/ma_bidirectional.py` correlates the **already extracted parent-seed SEC filings** against exact L1 names of GLEIF related companies, even when the child cannot file independently. This is recorded in `parent_sec_events` and `parent_side_decision`. It requires `EDGAR_MA` parser evidence, matching SEC filing pivot equal to the investigated parent, M&A-class event, and exact normalized child company name. The result remains `SEC_PARENT_TRANSACTION_CANDIDATE_REVIEW`, not confirmed M&A; no additional graph pivots and no ASM scope promotion. Parent-side investigation reuses the existing SEC root fetch and doesn't add an unbounded second network pass.

To wire an audited parent CIK: include a row like `549300J4U55H3WP1XT59,0000000000,VERIFIED,https://...evidence...` **only after replacing the illustrative zeros with an independently verified actual CIK and a real supporting source**. Do not treat an asserted relationship as crosswalk verification. The root legal-name LEI is anchored before SEC retrieval, allowing the CSV to apply.

Targeted local checks:
```bash
git pull --ff-only
python3 -m py_compile code/sec_identity_bridge.py code/ma_bidirectional.py code/run_company_ma_expansion.py
python3 -m unittest discover -s tests -p 'test_sec_identity_bridge.py' -v
python3 -m unittest discover -s tests -p 'test_ma_bidirectional.py' -v
python3 -m unittest discover -s tests -p 'test_ma_cross_source_integration.py' -v
```

Repeat the Bayer command with the same caps to compare results. If the parent still has `NO_SEC_IDENTITY`, that reflects the lack of an audited CIK, not a failure of the parent-side event match. There is no fabricated fallback CIK for Bayer, and no assumption that foreign public companies have SEC registrant identities. **Current scope excludes** historic CIK alias databases, automatically verified LEI–CIK links, content-level parent filing search for subsidiary aliases not extracted by the existing event parser, pagination/stratification of GLEIF L2 results, and GLEIF relationship period import repair.
