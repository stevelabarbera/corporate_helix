# Corporation Helix — MVP Getting Started

## Current working slice

The first working slice is **Corporate Attribution Resolver**:

1. SEC EDGAR Exhibit 21 -> normalized legal entities + subsidiary assertions.
2. GLEIF Level 1 JSON -> normalized legal-entity candidates.
3. RDAP domain registration JSON -> registrant organization/address evidence.
4. RDAP evidence -> ranked GLEIF candidate entities.
5. GLEIF Level 2 relationship JSON -> ownership relationship evidence.

A candidate match is **not** treated as proof of ownership. Ownership must be corroborated by GLEIF Level 2, EDGAR, or another ownership-capable provider.

## Run the tests

```bash
PYTHONPATH=. python -m unittest discover -s tests -v
```

## Normalize the existing SentinelOne EDGAR output

```bash
PYTHONPATH=. python -m src.corphelix.cli normalize-edgar \
  --input data/raw/edgar_sentinelone.json \
  --out data/normalized/edgar_sentinelone.json
```

Expected with the current snapshot:

```text
Wrote 29 EDGAR entities and 28 assertions...
```

The parser intentionally deduplicates the repeated Spain row in the source filing.

## Normalize a downloaded GLEIF Level 1 JSON file

```bash
PYTHONPATH=. python -m src.corphelix.cli normalize-gleif \
  --input /path/to/gleif-level1.json \
  --out data/normalized/gleif_entities.jsonl
```

The parser accepts nested GLEIF JSON and searches for records containing `LEI` + `Entity`, so it can work with the JSON-shaped records already inspected during research.

## Parse a downloaded GLEIF Level 2 relationship file

```bash
PYTHONPATH=. python -m src.corphelix.cli show-gleif-relationships \
  --input /path/to/gleif-relationships.json
```

## Map a saved RDAP response to GLEIF candidates

```bash
PYTHONPATH=. python -m src.corphelix.cli match-domain \
  --gleif /path/to/gleif-level1.json \
  --rdap-file /path/to/domain-rdap.json \
  --limit 10
```

Or perform a live RDAP lookup:

```bash
PYTHONPATH=. python -m src.corphelix.cli match-domain \
  --gleif /path/to/gleif-level1.json \
  --domain example.com \
  --limit 10
```

The live MVP adapter uses `rdap.org` for service discovery. Production should move to direct IANA RDAP bootstrap discovery.

## Current scoring behavior

The MVP deliberately errs toward false negatives rather than false positives:

- Legal/other name similarity generates candidates.
- Address similarity and jurisdiction/country are structured corroboration signals.
- A strong name alone does **not** produce a strong automatic match.
- Country conflict can reject an otherwise similar name.
- Missing registrant data is `unknown`, not negative evidence.
- Corporate ownership is a separate decision from entity identity.

The current matcher uses Python's built-in sequence similarity only as a bootstrap. The roadmap still calls for the planned Jaro-Winkler + Levenshtein + token ensemble and full GLEIF ISO 20275 legal-form normalization.

## Immediate next run

Use one of the GLEIF JSON files already downloaded locally and run `normalize-gleif`. If it parses successfully, choose a domain whose RDAP record exposes registrant organization information and run `match-domain` against that same GLEIF file.

If the GLEIF file does not parse, preserve it unchanged and adjust only `src/corphelix/providers/gleif.py`; do not reshape the raw input manually.

## Validated against real GLEIF daily delta (2026-08-04)

The GLEIF Level 1 adapter has been validated against `20260804-0800-gleif-goldencopy-lei2-last-day.json` (9,203 records).

Important distinction:
- `lei2-last-day.json` is a delta/change set. It is ideal for parser validation and incremental updates, but it is not a complete search corpus.
- `lei2-golden-copy.json` is the full Level 1 universe and should be used to bootstrap the local entity index.
- `rr-golden-copy.json` contains Level 2 relationship records and is the next integration target after the Level 1 index exists.

The real delta contains useful event evidence including `MERGERS_AND_ACQUISITIONS`, `ABSORPTION`, `DISSOLUTION`, `LIQUIDATION`, legal-name/address changes, and successor entities. The adapter preserves those fields rather than discarding them.
