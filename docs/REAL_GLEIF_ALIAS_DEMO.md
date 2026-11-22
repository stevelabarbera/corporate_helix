# Real GLEIF alias demonstration — acceptance exercise

This PR supplies a read-only, self-selecting demonstration against the existing independently verified 100-record Level 1 evidence database.

We directly inspected the user's uploaded `gleif_lei_tier1_sample.sqlite` and found **17** noncanonical name records. Actual source-backed examples from that specific sample:

| Historical / other name | Current name in GLEIF source record | LEI |
|---|---|---|
| Trustmark National Bank | Trustmark Bank | 01J4SO3XTWZF4PP38209 |
| CHALA ESTATES S.R.O. | GE AVIATION CZECH S.R.O. | 010CMKZ3VON21WF2ZD45 |
| IXIS ADVISOR FUNDS TRUST I | NATIXIS FUNDS TRUST I | 01YA4M3ZQ45K0V190G80 |
| CDC NVEST FUNDS TRUST I | NATIXIS FUNDS TRUST I | 01YA4M3ZQ45K0V190G80 |
| NEW ENGLAND FUNDS TRUST I | NATIXIS FUNDS TRUST I | 01YA4M3ZQ45K0V190G80 |

These are source-reported historical-name associations, **not** evidence of legal acquisition or current parent ownership. A verified sample does not prove that the existing earlier-snapshot Level 1 lookup includes the same LEIs.

## Execute

```bash
git fetch origin
git switch feat/real-gleif-alias-demo

python3 -m unittest discover -s tests -p 'test_real_gleif_alias_demo.py' -v
python3 -m unittest discover -s tests -p 'test_alias_identity_fallback.py' -v
python3 tests/test_root_entity_resolver.py

python3 code/demo_real_gleif_alias.py \
  --alias-db data/processed/gleif_lei_tier1_sample.sqlite \
  --lei-db data/processed/gleif_lei.sqlite \
  --rr-db data/processed/gleif_rr.sqlite
```

The demonstration queries actual alternate names from the staged DB, ensures the associated LEI is present in the existing Level 1 lookup, and checks that canonical-only seed discovery does not already cover the name. Only then does it invoke the real resolver with `allow_sample_aliases=True`. It requires `REVIEW_REQUIRED` and `LOW` confidence, otherwise aborts. The result includes source LEI, alias type, current source-record legal name, original ordinal, source archive checksum, and an explicit `ownership_verified:false`.

The script may return `NO_DEMONSTRABLE_ALIAS` (exit 2). That is **not a failure of evidence preservation**: it means the small sample or the existing LEI index did not yield a safe demonstrable new alias hit.

## Lean scaling decision after sample exercise

Do **not** stage all 3.4 million Level 1 full record blobs simply to support alias search.

Instead, build an **additive compact alias lookup** by streaming the existing immutable August 17 Level 1 archive once: preserve source archive checksum, every alias' LEI and source ordinal, raw name object (type/language), normalized search key, and source-file reference. Preserve the original source ZIP for record retrieval; don't claim a checksum is the source itself. Use a uniquely named new SQLite file and count/coverage reconciliation before eligibility. This can reuse the current review-only resolver lookup model or be adapted with minimal query changes. Keep source metadata and completeness distinct from confidence decisions.

The compact index would be a derived search aid, **not a replacement** for the full source archive or an alternative source of truth. Avoid calling an incomplete sample `NO_MATCH`, and never allow alias-only match to establish current ownership automatically.

## Outside scope

Full historical event interpretation, GLEIF feed expansion, publication pipeline, and broad alias fuzzy search remain deferred. Keep identity/M&A benchmark work moving.
