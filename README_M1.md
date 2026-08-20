# M1 — Canonical Evidence Foundation

This patch begins the provider/evidence foundation without changing the EDGAR fetcher.

## Added
- `EntityCandidate`
- `RelationshipAssertion`
- `Evidence`
- `ProviderResult`
- `CorporateDataProvider`
- `EdgarJsonAdapter`
- `canonicalize_edgar.py`

Raw files stay under `data/raw/`; canonical output should go under `data/processed/`.

### Sony
```bash
mkdir -p ./data/processed
python3 ./code/canonicalize_edgar.py --in ./data/raw/edgar_sony_vn.json --out ./data/processed/canonical_sony.json
```
Expected: about **28 entities / 28 relationships**.

### SentinelOne
```bash
python3 ./code/canonicalize_edgar.py --in ./data/raw/edgar_sentinelone_v4.json --out ./data/processed/canonical_sentinelone.json
```

This is not entity resolution yet. It is the provider-specific raw evidence → canonical evidence boundary.
