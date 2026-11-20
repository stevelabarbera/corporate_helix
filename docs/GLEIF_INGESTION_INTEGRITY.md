# GLEIF ingestion integrity and cardinality — findings and design decision

**Recorded:** 2026-11-20  
**Status:** Investigation and architecture decision; **not yet a production importer fix**  
**Scope:** GLEIF Level 1 (LEI2 identity) and Level 2 (RR relationships) Golden Copy ingestion, source-to-index fidelity, temporal evidence preservation  
**Related work:** PR #4 (RR historical/temporal audit), PR #5 (RR source-to-SQLite fidelity audit), PR #6 (Level 1/2 cardinality inventory)

## Executive summary

A **confirmed data-modeling defect** exists in `code/build_gleif_rr_index.py`: `relationship_periods()` keys a dictionary by `PeriodType`. When a single GLEIF relationship source record contains multiple periods of the **same** type, later entries silently overwrite earlier entries. There is no chronological sort or “newest wins” rule. The August 17, 2026 RR Golden Copy contains **seven supported records** with **two distinct `ACCOUNTING_PERIOD` entries each**, so **one accounting period is not represented in the current SQLite row for each of those seven records**. The unmodified source ZIP still retains both.

The decision is **not** to convert every field to one-to-many storage. Instead, inventory the source schema and observed cardinality, classify genuinely repeating structures, normalize those selectively, retain **complete original source evidence** (or a verified lossless immutable reference), and keep fast lookup indexes separate from the historical evidence store.

This is broader than the seven known period cases: we need to detect other fields vulnerable to overwrite, omission, or lossy flattening, especially Level 1 entity events, names, and successor identities, and Level 2 qualifiers. **A repeating source field does not automatically imply the current importer corrupts it**; map actual importer behavior before assigning defect status.

## Evidence and exact findings

### A. Level 2 source-to-index fidelity (PR #5)

Source: `20260817-0800-gleif-goldencopy-rr-golden-copy.json.zip`; compared to `data/processed/gleif_rr.sqlite` built from the same filename.

| Measure | Observed result |
| --- | ---: |
| Relationship source records scanned | 484,558 |
| Indexed, supported relationships | 258,887 |
| Unsupported relationship-type records | 225,671 |
| Indexed relationships matching **all 17 selected importer fields** | 258,887 |
| Field mismatches | 0 |
| Missing/extra index relationship keys | 0 / 0 |
| Duplicate supported source keys in snapshot | 0 |
| Supported records with two **different** `ACCOUNTING_PERIOD` values | **7** |

The selected fields agree **after applying the existing flattening logic**. This is important: 17/17 field equality **does not certify lossless ingestion**, because the comparator itself models one value per period type. Nor does it prove all raw JSON attributes were preserved or independently validate the source parser.

**Examples (source order; last value wins):**

| Source record number(s) | Accounting periods in original source order | Period retained by flat index |
| --- | --- | --- |
| 188860, 188861 | 2018-09-30 → 2019-09-30; 2017-09-30 → 2018-09-30 | **2017–2018 (older)** |
| 383353, 383354 | 1997-01-01 → 1997-12-31; 2016-01-01 → 2016-12-31 | **2016 (newer)** |
| 384343, 384344 | 2017-01-01 → 2017-12-31; 2016-01-01 → 2016-12-31 | **2016 (older)** |
| 463252 | 2019-07-01 → 2020-06-30; 2018-07-01 → 2019-06-30 | **2018–2019 (older)** |

The source retains timezone offsets; above is abbreviated for readability. These are accounting/reporting periods, **not evidence that an ownership relationship began or ended on those dates**.

### B. Source cardinality inventory (PR #6)

Tests: **4/4 passed** on the local machine.

**Level 2: full 484,558-record scan**, 65 observed JSON paths:

- `RelationshipPeriods.RelationshipPeriod`: **296,874 list occurrences** with multiple items (maximum 3), plus **187,611 object occurrences**. Most multi-item lists represent **different period types**, and the importer stores a separate column pair for each supported type. **Only the seven same-type duplicates above are confirmed period overwrites.**
- `RelationshipQualifiers.RelationshipQualifier`: 151,514 array occurrences, **41 with multiple values**, maximum 3. These qualifiers are not represented in the current `relationships` columns. Assess their semantics and coverage before assigning an ownership interpretation or deciding precise normalized storage.
- Seven repeated `ACCOUNTING_PERIOD` cases are reproduced in the cardinality inventory.

**Level 1: initial first 10,000-record sample**, 264 observed JSON paths:

| Source field path (within `Entity` unless otherwise noted) | Multi-item array occurrences | Max items in sample | Why investigate |
| --- | ---: | ---: | --- |
| `LegalEntityEvents.LegalEntityEvent` | 950 | 8 | Legal-history / change events |
| `OtherEntityNames.OtherEntityName` | 71 | 6 | Aliases and alternate names |
| `SuccessorEntity` | 1 | 2 | Entity continuity / succession |
| `LegalEntityEvents.LegalEntityEvent[].AffectedFields.AffectedField` | 1 | 2 | Nested event field references |
| `LegalAddress.AdditionalAddressLine` | 193 | 3 | Multiple address lines |
| `HeadquartersAddress.AdditionalAddressLine` | 125 | 3 | Multiple address lines |
| `OtherAddresses.OtherAddress` | 3 | 2 | Alternate addresses |
| `TransliteratedOtherAddresses.TransliteratedOtherAddress` | 323 | 2 | Transliterated address variants |
| `TransliteratedOtherEntityNames.TransliteratedOtherEntityName` | 1 | 2 | Transliterated names |
| `Extension.gleif:Geocoding` | 221 | 3 | One or multiple geocoding objects |

Level 1 `Extension.gleif:Geocoding` appears both as an object (3,809 occurrences) and as an array (221); `Extension` can be null. Additional nested repeating paths exist; the *full* JSON report is the complete audit artifact. **These figures are from a 10,000-record sample**, not 3-million-entity population counts. An occurrence is not always a distinct legal entity, particularly at nested paths.

**Next pending validation:** Full Level 1 cardinality scan against the August 17 ZIP. The user has been given:

```bash
python3 code/audit_gleif_cardinality.py \
  --level lei \
  --source "../Gleif_Golden_Copies/20260817-0800-gleif-goldencopy-lei2-golden-copy.json.zip" \
  --out data/processed/gleif_lei_cardinality_full.json
```

Do not represent that scan as completed until its results have been reviewed.

### C. Other ingestion and historical risks (different from cardinality)

1. Level 2 RR importer builds `relationships` keyed by `(child_lei,parent_lei,relationship_type)`, uses UPSERT, and **deletes/recreates its output DB on rebuild**. This index therefore does not preserve source observations across snapshots. This is a design gap, even though the August 17 single-snapshot duplicate-key audit returned zero.
2. Current Level 2 importer selects only direct/ultimate consolidation types. **225,671** other relationship records in this snapshot are excluded from the lookup index (fund management, subfund, feeder, international branch). These are intentionally unsupported by that index, **not proven parser errors**. Preserve their evidence in the future source store, then apply explicit semantics to any derived graph.
3. Level 1 Aug 4 source previously required one logged `b'},.'` repair; Aug 17 raw-byte scan found zero occurrences of that **specific pattern**. Absence of that pattern does **not** establish general JSON validity. Existing Level 1 source-repair behavior deserves independent validation and opt-in/fail-closed design.
4. Level 1 and Level 2 snapshot dates can differ. Record snapshot IDs and observed dates; do not assume cross-snapshot temporal alignment.
5. Legal consolidation, legal ownership, transaction/closing events, accounting period, effective period, registration time, and observation time are **different semantics**. The Bolthouse/Campbell root proposal illustrates why the current source snapshot cannot alone establish present-day ownership against dated divestiture evidence. Do not automatically suppress a GLEIF edge without confirming legal-entity identity and transaction scope.

## Approved engineering direction

1. **Measure before modeling.** Finish full Level 1 cardinality audit, review official GLEIF field schema, and inspect `build_gleif_lei_index.py` and `build_gleif_rr_index.py` **field-by-field** for truncation, first/last-value selection, skipped arrays, optional fields, and version-sensitive structures. Differentiate observed repetition from *actual confirmed ingestion loss*. Record an explicit disposition for each field: scalar column, normalized child table, raw-only evidence, deliberate derived omission, or unresolved pending source-schema review.
2. **Preserve original evidence.** Keep immutable source snapshot provenance and a complete source record or verified immutable lossless reference, with source identifier, member/path, snapshot date, content hash where feasible, and observation/build metadata. Historical provider observations must not overwrite one another. Selective normalization is for querying; raw preservation is the safety net.
3. **Normalize genuine repetitions.** Example: `relationship_observations` plus `relationship_periods` child rows storing period type, start/end, original source order, and stable observation linkage; allow multiple entries with the same period type. Review names/events/successors/qualifiers for similarly appropriate structures, including nested one-to-many fields.
4. **Retain performance.** Continue to support the existing fast `relationships` lookup (or a compatible derived view/table) without treating its single-value reporting columns as complete history. Make any selection policy explicit and versioned.
5. **Separate evidence from judgments.** Place source observations, interpreted corporate relationships, assessed effective dates, transaction events, and ASM scope recommendations in distinct layers. Account for conflicting authoritative sources and use review/uncertainty states.
6. **Migrate safely.** No destructive rebuild of existing user DBs for schema experimentation; new output path/migration strategy, independent fixture comparisons, count/hash/replay checks, and integration tests for the resolver/CLI. Test repeating same-type fields, object-versus-array shapes, missing/null values, older-last ordering, multi-snapshot temporal changes, and unsupported types.

## Proposed validation gates before calling ingestion lossless

- Full field-path and cardinality inventory for **both** levels, with source schema reconciliation.
- Mapping matrix for each source field: cardinality, stored destination, preservation status, transformation policy, test reference; explicit documented omissions.
- Independent structural parsing/record counting (RR audit currently uses the same parser as production, so parity is not independent evidence).
- Every source observation and repeated child element preserved or accounted for; totals and selected attributes compared against original raw records, not only against the old flattening function.
- Historical snapshots are append-only/deduplicated with reproducible provider/build identifiers.
- No regression in identity resolution, current/historical ownership safeguards, or performance-critical lookups.

## Immediate work queue

- [x] Confirm seven distinct repeated `ACCOUNTING_PERIOD` cases and existing last-item-overwrite bug.
- [x] Source-to-current-index 17-field fidelity and matching key audit for Aug 17 Level 2.
- [x] Full Level 2 cardinality inventory.
- [x] Initial 10,000-record Level 1 cardinality sample.
- [ ] Review complete Level 1 inventory once local run finishes; update this document with new data.
- [ ] Audit importer **field mapping and omitted structures**, cross-check official provider schema, and classify all discovered repeating paths.
- [ ] Author normalized evidence schema and append-only snapshot design; keep lookup backward compatibility.
- [ ] Implement migration/import with tests proving no source period or version is lost.
- [ ] Run end-to-end regression suite and evaluate current-versus-historical interpretations.
