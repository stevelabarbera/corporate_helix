# Compact GLEIF Level 1 alias index — MVP

Purpose: prove full-GLEIF historical and alternative legal-name search without duplicating millions of complete GLEIF JSON records into another SQLite database. This is an additive **read-only source-derived search aid**. The original ZIP remains authoritative.

The index contains a source manifest (level, source path, archive SHA-256, source record count, alias count, sample flag), one small `source_observation` row **only for alias-bearing source records**, and one `entity_name` row for **each** other/transliterated name. Each alias stores the original per-record ordinal, type/language-containing raw name object, LEI, and the original source record ordinal. **No full source JSON blobs, events, or successors are duplicated.**

### First: bounded trial (only 100 records)

From the `corporate_helix` repository root:

```bash
git fetch origin
git switch feat/compact-gleif-alias-index

python3 -m unittest discover -s tests -p 'test_compact_gleif_alias_index.py' -v

python3 code/build_compact_gleif_alias_index.py \
  --source ../Gleif_Golden_Copies/20260817-0800-gleif-goldencopy-lei2-golden-copy.json.zip \
  --out data/processed/gleif_alias_compact_100.sqlite \
  --max-records 100

python3 code/verify_compact_gleif_alias_index.py \
  --source ../Gleif_Golden_Copies/20260817-0800-gleif-goldencopy-lei2-golden-copy.json.zip \
  --db data/processed/gleif_alias_compact_100.sqlite
```

**Do not rerun the build on the same output path**: the writer intentionally refuses existing files. Pick a NEW name for subsequent experiments. The archive checksum is a checksum of the ZIP itself, not of a JSON record. The independent verifier rereads the original source using a different parser entrypoint and compares every alias tuple plus total source record count, including source records with zero aliases.

Expected trial status: builder `BUILT_UNVERIFIED`, verifier `PASS` and `is_sample=true`; compare the alias count with the earlier 100-record evidence staging sample (17 noncanonical name rows were previously observed).

The compact DB conforms to the *alias lookup* tables consumed by `root_entity_resolver.find_alias_seed_matches` (without storing `Entity.LegalName` rows). An existing demo using the compact DB would have `source_current_legal_name=null`, because the compact lookup purposely omits canonical legal-name records; current indexed name is still available separately from `lei_entities` but might use a different snapshot. This is an intentional metadata limitation, not a historical-name mismatch.

### Later: full dataset build (after trial pass)

```bash
python3 code/build_compact_gleif_alias_index.py \
  --source ../Gleif_Golden_Copies/20260817-0800-gleif-goldencopy-lei2-golden-copy.json.zip \
  --out data/processed/gleif_alias_compact_full.sqlite

python3 code/verify_compact_gleif_alias_index.py \
  --source ../Gleif_Golden_Copies/20260817-0800-gleif-goldencopy-lei2-golden-copy.json.zip \
  --db data/processed/gleif_alias_compact_full.sqlite
```

Full-source parsing and verification each independently stream the multi-million-record archive; they may take substantial resources/time. Do not conflate `is_sample=false` or a successful builder with independent verification, and do not deploy until the verifier passes. Also independently compare the final record count with the GLEIF archive's published/source metadata and reconcile known historical index snapshot differences. The verifier detects row omissions, wrong ordinals, mutated names, counts, and archive mismatch; it is not independent evidence of legal ownership.

### MVP limits / next work

- The resolver still uses bounded `LIKE` coarse candidate search; it can miss names beyond the 5,000-row cap. This index is **not yet a complete-recall matching engine**.
- Matching uses a review-only alias fallback and preserves collision candidates, not auto ownership attribution.
- The existing canonical LEI index and GLEIF RR relationship index are not rebuilt or replaced. Differing as-of snapshots require explicit provenance/reconciliation before authoritative claims.
- Full source references are via archive hash + original source ordinal and raw alias object; obtaining a complete source record requires reopening the original ZIP.
- An independently verified full compact alias DB is a meaningful M&A discovery step, but does not solve stale ownership or historical acquisition interpretation.

Tests should be run before full corpus. No existing data is overwritten.
