# M4.2 — GLEIF SQLite Auto-Enrichment

Drop these files into your repo at the matching paths, overwriting what's there:

- `code/providers/gleif_lei_lookup.py`   -> NEW FILE
- `code/providers/gleif_rr_adapter.py`   -> REPLACES existing
- `code/canonicalize_gleif_rr.py`        -> REPLACES existing
- `code/generate_corporate_seeds.py`     -> REPLACES existing

## What changed

1. gleif_lei_lookup.py (new): read-only wrapper around
   data/processed/gleif_lei.sqlite. lookup(lei) returns a LeiResolution
   with status RESOLVED / UNRESOLVED_RETRY / UNRESOLVED_TERMINAL.
   UNRESOLVED_TERMINAL is defined but not yet reachable — needs
   reporting-exception data (M4.5 scope).

2. gleif_rr_adapter.py: from_record() now accepts an optional lei_index.
   Resolution precedence: explicit --name override > SQLite index >
   bare-LEI fallback (UNRESOLVED_RETRY). resolution_status is now
   stamped onto the child (ProviderResult.metadata), the parent
   (EntityCandidate.attributes), and the relationship
   (child_resolution_status / parent_resolution_status in
   RelationshipAssertion.attributes) so it survives into the graph.

3. canonicalize_gleif_rr.py: auto-loads
   data/processed/gleif_lei.sqlite by default. New flags:
   --lei-db <path>   override the index location
   --no-lei-db       skip auto-enrichment entirely
   Manual --name/--jurisdiction flags still work and still win over
   the index (useful for tests/fixtures).

4. generate_corporate_seeds.py: previously scored any GLEIF-sourced
   edge as "high" confidence / SAFE_WITH_CONTEXT regardless of whether
   the counterpart name was real or a bare unresolved LEI. Now an
   unresolved resolution_status on either side downgrades the seed to
   "review" / REVIEW_REQUIRED, and tracks the worst status across all
   edges touching a given seed (new identity_resolution_status field,
   plus identity_resolution_status per relationship_evidence entry).

## Two things I found but did NOT fix (flagging for you)

- code/models.py (flat file) and code/models/ (the real package used
  everywhere) both exist. Python resolves the package first so nothing
  is broken today, but it's a landmine — worth deleting models.py.

- normalization/names.py, normalization/jurisdictions.py, and
  normalization/keys.py are missing entirely, even though
  normalization/pipeline.py and resolution/resolver.py both import
  them. This means the full pipeline (and the existing
  tests/test_gleif_rr_vertical_slice.py) can't currently run, separate
  from anything in M4.2. I did not try to reconstruct
  normalize_legal_name's legal-form-stripping logic myself since it's
  identity-comparison logic your own project rules treat as sensitive —
  didn't want to guess at matching behavior. Worth recovering from a
  backup if one exists, or flagging for a dedicated session.

## Tested (synthetic fixture, not your real 13GB index)

- Auto-resolves an LEI present in the index, no manual flags needed.
- Correctly tags a missing LEI as UNRESOLVED_RETRY (not dropped, not
  given an invented name).
- Manual --name/--jurisdiction override still takes precedence.
- Graceful fallback (with a printed note) when --lei-db points to a
  file that doesn't exist.
- Ran through the actual canonicalize_gleif_rr.py CLI end-to-end.
