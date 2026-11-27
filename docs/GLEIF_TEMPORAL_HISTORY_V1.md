# GLEIF relationship history — first correctness slice

2026-11-27, branch `eval/ma-recall-four-baseline`, PR #19.

## Existing work that this extends

- `code/root_entity_resolver.py:_relationship_applies_now` already checks current-snapshot `ACTIVE` and explicit relationship interval eligibility. That check **does not** prove current ownership, and cannot reconstruct historical status.
- `code/build_gleif_rr_index.py` already distinguished `RELATIONSHIP_PERIOD`, `ACCOUNTING_PERIOD`, and `DOCUMENT_FILING_PERIOD`. Its `relationship_periods` implementation previously used a dictionary indexed by type, silently flattening repeated types.
- Other GLEIF parsing in `code/providers/gleif.py` also uses a first-period projection; it has **not** been migrated in this slice. No alternative temporal truth source should be inferred from that projection.

## Changes

- The rebuild-only RR importer adds `relationship_periods` with ordered typed entries (`period_ordinal`), original raw JSON per period, plus raw JSON for the entire RR record on `relationships`. Existing flat start/end columns remain as **compatibility-only first-of-type projections**. Consumers needing complete periods must use the new table.
- `relationship_periods` is populated in the same DB transaction as the relationship row; supported entries retain duplicate period types and their input order.
- `relationships.first_seen_snapshot` and `last_seen_snapshot` are **the same source filename on a single fresh rebuild**. They do *not* establish real cross-snapshot observation history. The importer deletes/recreates its output DB; true multi-snapshot observation history requires a separate append-only audit table, not this field.
- `code/gleif_temporal.py` provides `CURRENT_SUPPORTED`, `CURRENT_UNRESOLVED`, `HISTORICAL_ONLY` as **support-level classifications**, not legal ownership verdicts. Relationship end is distinct from accounting end. `HISTORICAL_ONLY` needs inactive status and a bounded old relationship period; contradictory ACTIVE/ended periods remain unresolved. Missing, lapsed, stale and contradictory evidence must not become current supported.
- `CURRENT_SUPPORTED` currently uses a **conservative, provisional 730-day accounting recency heuristic** together with an active relationship, published registration, and an eligible explicit relationship period. The threshold is not an official GLEIF rule or ownership confirmation; it should be calibrated against historical snapshots.
- `code/providers/gleif_relationship_provider.py` reads the new period table when present, attaches all typed periods and the assessment to each review-only GLEIF edge. Legacy indexes remain readable with `period_provenance=LEGACY_FLATTENED_INDEX`. Their missing duplicate periods cannot be inferred.

**Non-negotiable trust boundary**: none of these classifications grants accepted fact status, recursive pivots, M&A event confirmation, or ASM scope authorization. `CURRENT_SUPPORTED` means *current-snapshot evidence is internally compatible and recent enough for investigation*, not ownership proven.

## Local validation

```bash
git pull --ff-only
python3 -m py_compile code/build_gleif_rr_index.py code/gleif_temporal.py code/providers/gleif_relationship_provider.py
python3 -m unittest discover -s tests -p 'test_gleif_temporal.py' -v
python3 -m unittest discover -s tests -p 'test_ma_cross_source_integration.py' -v
python3 -m unittest discover -s tests -p 'test_ma_bidirectional.py' -v
```

**Do not overwrite the existing RR index yet.** Rebuild into a *new* filename using your actual source zip, then compare row counts and targeted Bayer Animal Health / Monsanto examples before switching the default index. Existing indexes have already lost repeated period entries, so they cannot be repaired without the original source ZIP.

## Still open

1. Validate full Golden Copy import and period counts against the raw source, including duplicate relationship-record keys and repeated period classes. The existing composite unique index retains only one row per pair/type, which may still hide multiple source records for the same key; a versioned observation table is required for complete record-level losslessness.
2. Add immutable multi-snapshot first/last-seen observation history, rather than treating rebuild metadata as historical truth.
3. Migrate the alternative `code/providers/gleif.py` parser and the root resolver to shared period-aware assessment, after checking baseline root resolution regression risk.
4. Quantify conflicts, stale periods and missing fields across the full dataset; calibrate recency instead of relying on a provisional fixed heuristic.
