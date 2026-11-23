# Identity anchoring safeguard (MVP)

## Problem

The real-data Sempra query matched `SEMPRA ENERGY TRADING LLC` as a *phrase* match, then graph traversal ranked `NATWEST GROUP PLC` as a proposed `root`. The output was `REVIEW_REQUIRED` rather than auto-resolved, but exposing NatWest in the endorsed-root field remained misleading. SentinelOne similarly produced an Indian regional entity as a proposed root for a broad company query. The previous read-only diagnostic flagged both without changing resolver behavior.

## New decision contract

A root can be populated only when all of the following hold:
1. There is exactly **one** candidate with a normalized full-string match to a *canonical GLEIF current legal name*, not merely a token substring or historical alias.
2. Graph ranking's top entity is the **same LEI** as that exact canonical anchor. A parent discovered solely via consolidation traversal remains an exploratory lead.
3. The existing auto-resolution confidence logic accepts the anchored identity; inactive / conflicted / otherwise review-only decisions must return `root=null`.

Otherwise, `REVIEW_REQUIRED` with `root=null` (or `NO_MATCH` for absent seeds). **All exploratory matches and graph-ranked candidates remain in `seed_matches` and `candidates`.** This ensures no lost discovery evidence while preventing upstream parent recommendations from looking endorsed. Review-required is not proof that an identity is wrong; exact canonical matching is a conservative *input gate*, not independent proof of ownership.

The rule intentionally changes previous permissive behavior: single partial names like `Hawkeye Innovations`, abbreviations like `NTT`, and historical aliases now generate reviewable leads, not automatic root approvals. An exact match with a parent ranked higher is also review-only.

**Important:** This safeguards the `root` field; it does not automatically verify any parent-child ownership or any M&A event. Alias recall and LEI snapshot coverage remain separately open.

## Run on Mac

```bash
git fetch origin
git switch fix/require-exact-identity-anchor

python3 -m unittest discover -s tests -p 'test_identity_anchoring.py' -v
python3 -m unittest discover -s tests -p 'test_identity_quality_gates.py' -v
python3 -m unittest discover -s tests -p 'test_alias_identity_fallback.py' -v
python3 -m unittest discover -s tests -p 'test_alias_discovery_benchmark.py' -v
python3 tests/test_root_entity_resolver.py

python3 code/audit_identity_quality.py \
  --company "Sempra Energy" \
  --company "SentinelOne" \
  --alias-db data/processed/gleif_alias_compact_full.sqlite \
  --out data/eval_study/identity_anchoring_v1.json
```

The new diagnostic fields are:
- `proposed_root`: accepted identity root; should be `null` for Sempra and SentinelOne if their local indexes still reproduce the previous queries.
- `exploratory_top_candidate`: previously top-ranked candidate graph entity, **not accepted**; Sempra may still show NatWest here. This is expected: evidence was deliberately retained.
- `quality_warnings`: including `NO_EXACT_CANONICAL_NAME_IDENTITY_ANCHOR`, `EXPLORATORY_PARENT_FROM_RELATIONSHIP_TRAVERSAL`, and `EXPLORATORY_ROOT_LACKS_VERIFIED_QUERY_IDENTITY`.

For exact legal-name queries, successful auto-resolution now asserts only an anchored GLEIF identity, **not** a verified group-parent ownership or current ASM ownership relationship.

Expected synthetic regression suite: six new tests plus previous suites. Real-data rerun results still need to be observed, and frozen 30-case cohort must be reevaluated for expected declines in auto-approval rate.
