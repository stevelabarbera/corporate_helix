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

**Level 1: full August 17 source scan completed, 3,403,856 records**, 283 observed JSON paths; compared with 10,000-record preliminary sample (264 paths). Local result was submitted 2026-11-20. The full scan used `ijson` over the source ZIP and printed `coverage: full_requested`; this establishes that the audit iterator reached the end, **not** independent proof of GLEIF source schema completeness or equivalence to every destination field.

| Source field path (within `Entity` unless otherwise noted) | Multi-item array occurrences | Max items | Why investigate |
| --- | ---: | ---: | --- |
| `LegalEntityEvents.LegalEntityEvent` | **348,328** | 28 | Entity changes, events and history |
| `LegalEntityEvents.LegalEntityEvent[].AffectedFields.AffectedField` | **747** | 53 | Nested event field references |
| `OtherEntityNames.OtherEntityName` | **52,453** | 32 | Alternate names and aliases |
| `SuccessorEntity` | **570** | 53 | Multiple potential successor links |
| `LegalAddress.AdditionalAddressLine` | **324,833** | 3 | Multiple address lines |
| `HeadquartersAddress.AdditionalAddressLine` | **238,144** | 3 | Multiple address lines |
| `OtherAddresses.OtherAddress` | **44,080** | 2 | Additional addresses |
| `OtherAddresses.OtherAddress[].AdditionalAddressLine` | **5,114** | 3 | Nested address lines |
| `TransliteratedOtherAddresses.TransliteratedOtherAddress` | **77,491** | 2 | Address transliterations |
| `TransliteratedOtherAddresses.TransliteratedOtherAddress[].AdditionalAddressLine` | **7,433** | 3 | Nested transliterated address lines |
| `TransliteratedOtherEntityNames.TransliteratedOtherEntityName` | **1,257** | 4 | Transliterated names |
| `Extension.gleif:Geocoding` | **210,035** | 4 | Multiple geocoding observations |
| `Registration.OtherValidationAuthorities.OtherValidationAuthority` | **22,509** | 5 | Multiple validation authorities |

**Shape variation:** `Extension.gleif:Geocoding` was an **object** 1,359,707 times and an **array** 210,035 times. `Extension` was an object 3,402,841 times and `null` 1,015 times. Do not assume a singular object path is always scalar.

**Interpretation safeguards:** These are counts of *array instances containing two or more items*, not counts of individually lost source values. Nested paths can occur more than once per entity, and an array is not necessarily an ownership relationship or an M&A event. Each field must still be inspected against the Level 1 importer and provider schema before asserting loss. The earlier first-10,000 record sample is now superseded for population cardinality statistics by the complete scan.

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
- [x] Review complete Level 1 inventory (3,403,856 records; 283 observed paths) and record findings above.
- [ ] Audit importer **field mapping and omitted structures**, cross-check official provider schema, and classify all discovered repeating paths.
- [ ] Author normalized evidence schema and append-only snapshot design; keep lookup backward compatibility.
- [ ] Implement migration/import with tests proving no source period or version is lost.
- [ ] Run end-to-end regression suite and evaluate current-versus-historical interpretations.

## First enforcement increment: ingestion contract gate (PR #7)

`code/check_gleif_ingestion_contract.py` reads the **full** cardinality report JSON for either level. It creates a candidate frozen field-shape baseline, detects new paths, novel types, newly repeated arrays, larger array sizes, disappeared paths, and flags repeating source fields not yet reviewed. It explicitly reports the major known repeating fields as **unpreserved** or **partially flattened** in the current query-only indexes. It exits with code 2 for unresolved findings. This is a **read-only preflight/prototype gate**, not wired to the production importer and not evidence that the index is currently safe.

Field-level mapping review of `code/build_gleif_lei_index.py`: `flatten_record()` selects **19 scalar identity/registration columns** (including normalized legal name) and **does not ingest** legal entity events, other names, successor entities, other validation authorities, geocoding, or full address-line collections. The omissions are real in this **query-only index**; classifying them as data corruption would be misleading because this importer never claimed to store those structures. The original source ZIP is still available outside the DB. No immutable source observation table is implemented yet. `code/build_gleif_rr_index.py` has a confirmed overwrite for repeated same-type periods and omits qualifiers and unsupported relationship types from the lookup index.

**Next implementation requirements, still open:** independent raw source/parser validation; immutable source snapshots and per-record raw evidence with hashes; normalized one-to-many child tables; source-to-new-storage replay parity; opt-in repair and robust fail-closed import; staged/published-only-after-validation production integration; end-to-end resolver regressions. An audit report alone must never make the ingest pipeline claim losslessness.

Local usage after branch checkout:

```bash
python3 -m unittest discover -s tests -p 'test_gleif_ingestion_contract.py' -v

python3 code/check_gleif_ingestion_contract.py \
  --audit data/processed/gleif_lei_cardinality_full.json \
  --baseline-out data/processed/gleif_lei_candidate_baseline.json \
  --out data/processed/gleif_lei_contract_report.json
```

The second command is **expected to exit 2 and report BLOCKED**, since this is an honest account of the current index limitations. Creating a *candidate* baseline does not approve the schema or waive missing preservation.
