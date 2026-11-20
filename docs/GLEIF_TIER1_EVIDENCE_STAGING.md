# Tier 1 GLEIF evidence staging (MVP-scoped proof of concept)

This component is **additive** to the existing Level 1 and Level 2 SQLite lookup indexes. It is not a replacement for them and does not alter identity root decisions.

## Tier 1 field mapping (verified from current importer source)

| Field | Current `build_gleif_lei_index.py` behavior | Staging `build_gleif_tier1_evidence.py` |
| --- | --- | --- |
| LEI + current legal name | Selected, scalar | LEI identifier + current name child |
| Registration status, last update | Selected, scalar | Retained inside compressed entire parsed record |
| OtherEntityNames / alternative names | Not selected; no aliases table | Every name with source order, type in raw child JSON |
| TransliteratedOtherEntityNames | Not selected | Every name in source order |
| LegalEntityEvents | Not selected | Every event as original parsed JSON object, incl. nested affected fields |
| SuccessorEntity | Not selected | Every successor as original parsed JSON object |
| Level 2 relationship periods | Typed dictionary with last same-type item overwriting previous | Every typed period and ordinal; no dictionary collapse |
| Level 2 qualifiers | Not selected | Every qualifier as original parsed JSON object |
| Unsupported Level 2 relationship types | Skipped | Stored in evidence source_observation (all parsed relationship types) |

This is an **index scope limitation** for Level 1 aliases/events, not proof of accidental overwrite. The **Level 2 period overwrite** is confirmed. Additional Level 1 alias-to-resolver integration remains a separate MVP work item.

## What the prototype actually preserves

- Original input ZIP/file (which the user must retain) is identified by archive SHA-256 and absolute path.
- Every parser-returned record is stored as **compressed, canonical re-serialized JSON** plus a SHA-256 of those stored bytes. Every stored record hash is replay-verified. This retains parsed JSON structures, including Tier 2/3 fields, for later derivation.
- Tier 1 repeating structures are also queryable via child tables and maintain original array order.
- The original archive is the **byte-level authority**. Re-serialized JSON is **not byte-identical** to the source, so do not claim this is a forensic byte-exact source extraction.
- Existing output DBs are never overwritten. A new database is created exclusively at a user-selected path. Staging of an incomplete sample is flagged in `source_snapshot.is_sample`.

**Open before production:** independent Level 2 parser and full source-record count verification; end-to-end data-field fidelity beyond count/hash checks; staging atomicity and crash recovery; zip/archive lifecycle and durable backup; alias integration with resolver and matching controls; the effect of `ijson` Decimal values on serialization (currently fail-closed); migration and publish after tests. Full Level 1 evidence may consume considerable disk and build time. Do **not** run it against the 3.4-million entity file as the first experiment.

## Safe local test

```bash
git fetch origin
git switch feat/gleif-tier1-evidence
python3 -m unittest discover -s tests -p 'test_gleif_tier1_evidence.py' -v

# The 100-record sample is intentionally staged in its OWN database.
python3 code/build_gleif_tier1_evidence.py \
  --level lei \
  --source "../Gleif_Golden_Copies/20260817-0800-gleif-goldencopy-lei2-golden-copy.json.zip" \
  --max-records 100 \
  --out data/processed/gleif_lei_tier1_sample.sqlite
```

The output location **must not already exist**. To rerun, choose a different output filename; do not remove a database unless you have independently confirmed it is only an expendable test artifact.

## Next acceptance gates

1. Four new unit tests green: no name/event/successor loss, duplicate same-type period preservation, preserve all qualifiers, and no-clobber target.
2. Real 100-record staged trial and explicit source-to-staged comparison on the sample, including nested collections.
3. Verify source record counts with an independent streaming parser for Level 2 (currently reuses the legacy line parser).
4. Expose aliases in identity lookup **without** promoting name evidence into confirmed ownership.
5. Introduce the actual period child relation to a compatible production read model only after resolver regression tests.
6. Return to existing identity evaluation and M&A roadmap; do not pursue full Tier 2/3 normalization as a prerequisite.
