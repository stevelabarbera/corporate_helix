# GLEIF Tier 1 independent evidence verification — targeted trial

**Scope:** PR #9. This adds a verifier separate from the importer to compare each staged observation with the original GLEIF JSON source record, including queryable child fields. Does not modify the existing `gleif_lei.sqlite` or `gleif_rr.sqlite` indexes.

## Independent replay

`code/verify_gleif_tier1_evidence.py` reads **both levels** using `ijson.items(..., "records.item")` directly from ZIP/uncompressed JSON, instead of the existing Level 2 line-oriented parser. It reads the staged evidence database read-only and verifies:

- Original source archive SHA-256 matches the staged snapshot.
- Selected source record ordinals exist and their parsed JSON object trees equal the stored compressed JSON.
- SHA-256 over each stored compressed record's decompressed content equals the recorded hash.
- Every staged name, alias, translated name, legal entity event, successor, relationship period, and qualifier corresponds to the original source's element **in order**.
- Queryable name/normalized-name fields and relationship period type/start/end columns match the original source, not just the raw JSON copies.
- Total observation/child-row counts match each other and the source elements checked.

It returns status `PASS` or `FAIL` (exit 2 on mismatch). This is **source-based validation**, not the earlier importer-vs-itself field comparison. It is parser-level JSON fidelity, **not** byte-identical recovery of original source token spacing or independent validation of GLEIF's published schema.

## Known seven RR cases

`build_gleif_tier1_evidence.py` now accepts `--record-ordinals`. It streams past intervening source records but **only stages the specified ones**. This allows checking the seven proven repeated-accounting-period cases while avoiding staging the full RR corpus:

188860, 188861, 383353, 383354, 384343, 384344, 463252.

These are **source record ordinal numbers**, not LEIs or SQLite primary keys. The original source ZIP must match the August 17, 2026 snapshot used to obtain them. This option is mutually exclusive with `--max-records`.

## Run on the developer Mac

```bash
git fetch origin
git switch feat/gleif-evidence-verification

python3 -m unittest discover -s tests -p 'test_gleif_evidence_verification.py' -v

# Verify previously staged 100-record Level 1 sample:
python3 code/verify_gleif_tier1_evidence.py \
  --source "../Gleif_Golden_Copies/20260817-0800-gleif-goldencopy-lei2-golden-copy.json.zip" \
  --db data/processed/gleif_lei_tier1_sample.sqlite \
  --out data/processed/gleif_lei_tier1_verified.json

# Stage ONLY the seven known Level 2 period-overwrite records:
python3 code/build_gleif_tier1_evidence.py \
  --level rr \
  --source "../Gleif_Golden_Copies/20260817-0800-gleif-goldencopy-rr-golden-copy.json.zip" \
  --record-ordinals 188860 188861 383353 383354 384343 384344 463252 \
  --out data/processed/gleif_rr_tier1_seven_cases.sqlite

# Independently verify source-to-stage fidelity:
python3 code/verify_gleif_tier1_evidence.py \
  --source "../Gleif_Golden_Copies/20260817-0800-gleif-goldencopy-rr-golden-copy.json.zip" \
  --db data/processed/gleif_rr_tier1_seven_cases.sqlite \
  --out data/processed/gleif_rr_tier1_verified.json
```

**No overwrite:** The evidence builder refuses an output file that already exists. Choose another sample DB filename if repeating an experiment.

## Scope boundaries

- The Level 1 evidence builder's `iter_source` uses streaming `ijson`; the verifier separately scans the ZIP. This is an independent traversal, but both rely on the same underlying JSON library and archive bytes.
- The Level 2 staged source parser is still the legacy RR line iterator. The verifier's independent structural `ijson` reader is intended to catch record mismatch or missing records on selected ordinals.
- A pass on only seven RR records **does not prove complete full-corpus ingestion**. A later complete scan should independently reconcile full record counts and all element counts.
- The evidence staging DB is still a proof of concept; its connection to the resolver and validated publication process is not implemented.
- Alias integration with identity-resolution confidence safeguards, and an effective-period-sensitive read model, remain the next MVP tasks.
