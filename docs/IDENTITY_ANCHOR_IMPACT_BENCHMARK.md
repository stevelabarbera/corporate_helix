# How much did identity anchoring change our approvals?

This evaluation runs the **actual before and after resolver implementations** against the **same local LEI, relationship and alias SQLite indexes**. The old resolver is loaded at the exact Git commit corresponding to `origin/feat/identity-quality-gates` (the pre-safeguard version); the current checked-out `root_entity_resolver.py` implements the new exact-identity gate. Both implementations are fingerprinted in the output.

## Use

```bash
git fetch origin
git switch eval/identity-anchor-impact-cohort
python3 -m unittest discover -s tests -p 'test_identity_anchor_impact_benchmark.py' -v

python3 code/benchmark_identity_anchor_impact.py \
  --out data/eval_study/identity_anchor_impact_cohort_v1.json
```

The script uses a fixed RNG seed to construct an approximately 100-query diagnostic cohort directly from your real GLEIF indexes, with six strata:
- **40 general exact legal names**, sampled from ACTIVE indexed entities.
- **Up to 20 relationship-child exact legal names**, sampled from entities with ACTIVE indexed Level 2 consolidation relationships to test parent ranking pressure.
- **10 inactive exact legal names**, to test lifecycle/abstention.
- **Up to 15 shortened name probes** derived from sampled names, deliberately not assumed to be identity proof.
- **Up to 12 historical/alternative aliases** from the verified compact index, whose LEIs are also present in the canonical index.
- **2 known risk queries**: Sempra Energy and SentinelOne.

The actual cohort size may be smaller if a stratum has fewer qualified entries or duplicates with another. Counts and every query are preserved in the output under `frozen_cohort`. All sampling is repeatable against unchanged input DBs, but it is **purposefully stratified, not statistically representative**. Do not generalize aggregate percentages to the whole corporate population.

To reuse exactly those names later, point the same script at the previous output:

```bash
python3 code/benchmark_identity_anchor_impact.py \
  --cohort data/eval_study/identity_anchor_impact_cohort_v1.json \
  --out data/eval_study/identity_anchor_impact_cohort_v2.json
```

### Metrics

Each stratum reports before/after `AUTO_RESOLVED` and `REVIEW_REQUIRED` counts, `auto_to_review` transitions, changed decisions, suppressed endorsed roots, seed-set changes, and whether top exploratory candidates changed. Individual query rows retain the names and LEIs of endorsed and exploratory roots.

An increase in `REVIEW_REQUIRED` can be a **safety improvement** for partial names but may indicate lost useful automation for exact legal names. The paired comparison quantifies this trade-off without guessing.

### What it does not measure

- **No independently scored precision, recall, or parent accuracy**; output labels these `NOT_SCORED`.
- Historical alias/short-name provenance is **not a verified company identity**.
- The LEI and RR indexes may be different snapshots, and alias lookup may be truncated by an existing 5,000-row coarse search cap.
- This is **not** the previously discussed frozen 30-company identity benchmark; it is a new locally sampled diagnostic cohort and does not replace that benchmark.
- Sampling `expected_source_lei` captures the source LEI behind an exact legal-name query, but does not establish parent correctness or exclude same-name collisions.
- All databases are read-only. The results JSON is created with exclusive file mode and will not overwrite an existing report.

If exact-name cases lose many automatic resolutions, inspect why before relaxing the integrity boundary. The next work should be independent identity labels, stronger seed adjudication for collision cases, and a strictly evidence-backed way of accepting parent roots.
