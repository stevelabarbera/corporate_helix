# Identity quality gates: Sempra wrong-root stress test + alias index reconciliation

This is a **read-only diagnostic**, not a claim that the resolver has been fixed and not an automatic ownership gate. The prior 30-company benchmark contains an independently documented failure pattern: `Sempra Energy` matched `SEMPRA ENERGY TRADING LLC`, then relationship traversal proposed `NATWEST GROUP PLC`. The proposed parent was unsupported for the intended queried company, even while the resolver asked for review. That demonstrates why *candidate identity* and *parent traversal* must be judged independently.

## Run with your existing verified full index

```bash
git fetch origin
git switch feat/identity-quality-gates

python3 -m unittest discover -s tests -p 'test_identity_quality_gates.py' -v
python3 tests/test_root_entity_resolver.py

python3 code/audit_identity_quality.py \
  --company "Sempra Energy" \
  --company "SentinelOne" \
  --alias-db data/processed/gleif_alias_compact_full.sqlite \
  --out data/eval_study/identity_quality_semprasentinel_v1.json
```

The output shows:
- Full-population alias-bearing LEI coverage against the canonical index: present/missing counts and up to ten missing example LEIs.
- Source archive SHA and source row counts from the alias manifest. **LEI presence is not snapshot-date equality**.
- Per-query matched seeds, current indexed names, whether the input exactly matches those names, root candidate, and non-verdict warnings for mismatched name anchors or traversal-only parent proposals.
- `identity_correctness`, `proposed_root_correctness` = `NOT_SCORED`; `ownership_verified=false`. Neither the original benchmark's known problem nor this script automatically adjudicates real ownership.

**Warning interpretation:**
- `NO_EXACT_CANONICAL_NAME_IDENTITY_ANCHOR`: candidate names are only phrase matches or aliases; no independent identity proof. This is a diagnostic, not a blanket rejection of valid partial names.
- `PROPOSED_ROOT_FROM_RELATIONSHIP_TRAVERSAL`: selected candidate is upstream, not itself the seed legal entity.
- `ROOT_NOT_VALIDATED_AGAINST_QUERY_IDENTITY`: an upstream root was proposed even though input lacked an exact canonical anchor.
- `AUTOMATIC_SELECTION_WITHOUT_EXACT_CANONICAL_NAME`: potential policy gap to examine; existing resolver behavior is unchanged.

### Next gate: independently scored labels

Recover the original *frozen* 30-company cohort; labels should distinguish (a) correct target LEI, (b) correct root *as-of date*, and (c) acquisition or divestiture event with its dated disclosure. Do not infer those from GLEIF ACTIVE alone. Quantify false proposed roots and review burden separately from false auto-decisions. No proprietary M&A or asset inventory is needed to run this identity diagnostic.

The live canonical and RR SQLite databases, compact alias index, and original GLEIF ZIP are only read. Output path is exclusive (must be new). This PR is stacked on #13 and does not merge prior PRs.
