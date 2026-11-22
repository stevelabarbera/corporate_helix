# Paired alias discovery benchmark (MVP)

## Why this matters

We now have 646,273 source-verified alternative/historical names associated with 548,191 legal entities from the August 17, 2026 GLEIF Level 1 Golden Copy. The next question is measurable **incremental identity candidate discovery**, not whether the alias index was built successfully.

The previous 30-case identity benchmark had 5 AUTO_RESOLVED / 24 REVIEW_REQUIRED / 1 NO_MATCH, but **zero ground-truth scored cases**. The names of the frozen 30-case cohort are not currently stored as a checked-in file in this PR's base branch. Therefore, do not use the built-in five-name smoke cohort as if it were the original 30-case benchmark.

## Run after switching branch

```bash
git fetch origin
git switch feat/alias-discovery-benchmark
python3 -m unittest discover -s tests -p 'test_alias_discovery_benchmark.py' -v

python3 code/benchmark_alias_identity_discovery.py \
  --alias-db data/processed/gleif_alias_compact_full.sqlite \
  --out data/eval_study/alias_discovery_smoke_v1.json
```

Built-in smoke queries: `Trustmark National Bank`, `IXIS ADVISOR FUNDS TRUST I`, `CHALA ESTATES S.R.O.`, `Sempra Energy`, `SentinelOne`. These are **illustrative smoke probes, not independently labeled truth and not the prior 30-case cohort**. A historical name can already have been discovered under a legal-name phrase, so the runner measures genuine incremental seeds rather than assuming each example is new.

To reuse the exact frozen cohort once its names are retrieved from your earlier local evaluation, save a plain text file (one company per line) or a JSON list. Then:

```bash
python3 code/benchmark_alias_identity_discovery.py \
  --cohort path/to/frozen_30_company_cohort.txt \
  --alias-db data/processed/gleif_alias_compact_full.sqlite \
  --out data/eval_study/alias_discovery_frozen30_v1.json
```

Existing output paths are refused, not overwritten. The canonical and alias arms run sequentially against the same unchanged LEI/RR databases. Run the independent compact source verifier separately (PR #12 was already reported to pass 3,403,856 source records and 646,273 aliases).

### Metrics

- Baseline and alias-enabled counts by `AUTO_RESOLVED`, `REVIEW_REQUIRED`, `NO_MATCH`
- Queries with new candidate seed LEIs, incremental query/LEI pairs
- Queries that changed from no seed to some candidate seed
- Exact per-company seed LEIs, proposed root LEIs, decision reason and confidence
- Explicit `identity_correctness: NOT_SCORED`, `m_and_a_recall: NOT_SCORED`, and `ownership_verified: false`

No unsourced claim of improved precision, acquisition recall, or correct parent selection is made.

### Important limitations / acceptance gates

1. The resolver is **fallback-only**: aliases are consulted only when canonical legal names return zero seeds. It does not expand candidate coverage for already matched companies. This intentionally keeps decision behavior conservative.
2. Existing bounded `LIKE` first-token retrieval has a 5,000-row cap. A missed alias in the benchmark may reflect truncation or tokenization rather than genuine absence. Until exhaustive recall is established, numbers are **observed discoveries/lower bounds**.
3. Canonical LEI index and compact alias archive may have been built from different snapshots. The script prints canonical index metadata (if present) and source archive SHA but does **not** claim their LEI sets or timestamps are aligned.
4. No independent identity-root ground truth exists for this cohort. In particular, prior Sempra → NatWest proposed-root error is not fixed by merely discovering more aliases.
5. No verified M&A outcome is scored. For that, a separate gold set of acquisitions and divestitures with dated independent evidence is required.

After establishing paired baseline/deltas, the next implementation priority is (a) canonical/alias LEI snapshot reconciliation, then (b) removal of coarse search truncation with deterministic coverage/retrieval tests, then (c) independent identity labels and M&A ground truth.
