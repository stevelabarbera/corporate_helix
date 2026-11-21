# Alias-aware identity resolution — MVP review-only fallback

The resolver now accepts optional `alias_db=` pointing at a **staged Level 1 GLEIF evidence database**. It retains the existing direct legal-name matching behavior. Only when there are **no canonical legal-name seeds** does it search alternate and transliterated names.

## Trust boundary

- Every alias seed carries its current indexed legal name/LEI plus `matched_name`, `alias_source_path`, `alias_raw_value_json`, and source record ordinal.
- Alias matching is limited to complete normalized token phrases; SQL LIKE is only candidate retrieval.
- **All alias-only roots are `REVIEW_REQUIRED` with `LOW` confidence**, even with apparently unique candidates or converging graph edges. Historical name evidence is not current corporate ownership.
- Multiple LEIs for the same alias remain separate candidates. Missing LEIs in the existing Level 1 lookup index are not used.
- SQL reads the evidence database in read-only mode.
- An incomplete evidence sample is rejected by default. `--allow-sample-aliases` explicitly enables a demonstration; an absent alias result in this mode is `INSUFFICIENT_EVIDENCE`, not a definitive `NO_MATCH`.

## Validation / constraints

The previous 100-record Level 1 evidence sample was independently source-verified (PR #9), but is intentionally too limited for meaningful real-world alias coverage. Using it is a **code-path demonstration only**. A complete and independently verified Level 1 snapshot is required before relying on alias search in real company discovery. The fallback does not build a production alias index or migrate the live LEI database.

Current retrieval is bounded to 5,000 coarse alias rows, and matching can miss candidates outside that cap; there is not yet a source-exhaustion or complete-recall guarantee. `source_snapshot.is_sample=0` is ingestion metadata rather than a substitute for independent completeness validation. This is intentionally conservative and MVP-scoped.

## Local test

```bash
git fetch origin
git switch feat/alias-aware-identity-review
python3 -m unittest discover -s tests -p 'test_alias_identity_fallback.py' -v
```

Optional demonstration against the existing **100-record sample** (unlikely to match an arbitrary brand):

```bash
python3 code/resolve_alias_aware_company.py \
  --company "A historical legal name present in the sample" \
  --alias-db data/processed/gleif_lei_tier1_sample.sqlite \
  --allow-sample-aliases
```

To inspect the names actually available in that verified sample, without guessing:

```bash
python3 - <<'PY'
import sqlite3
c=sqlite3.connect('data/processed/gleif_lei_tier1_sample.sqlite')
for r in c.execute("""
SELECT n.name, o.record_identifier, n.source_path
FROM entity_name n JOIN source_observation o USING(observation_id)
WHERE n.source_path != 'Entity.LegalName' AND n.name IS NOT NULL
LIMIT 10
"""): print(r)
c.close()
PY
```

To use a **complete** Level 1 staged DB in the future, omit `--allow-sample-aliases`.

## Next acceptance steps

1. Run new alias fallback unit tests and the existing resolver regression suite.
2. Demonstrate one alias from the verified staging sample in review-only mode, and verify canonical resolution behavior does not regress.
3. Prepare a *complete* Level 1 evidence snapshot with an independent record-count reconciliation before production alias discovery; optimize lookup and verify archive date alignment.
4. Revisit alias rankings, collision handling, freshness, schema type classification, and full source exhaustion; never elevate alias evidence alone to automatic ownership.

This PR is stacked on #9. None of these changes automatically deploy to main.
