# Helix backlog

Parked work, each with the trigger that put it here and the condition for picking it up.
Last updated 2026-10-13. Decisions live in the `DECISIONS_*.md` files; this is only the queue.

## Foundation (do first -- decides whether the items below are worth doing)

Trigger: every new company has surfaced a document or format Helix missed (Alsid SAS, Einride/Flipturn).
Those misses are two different classes: *coverage gaps* (form never fetched: 6-K/20-F/40-F, older
filing pages) and *extraction failures on fetched documents* (the "AB" suffix, cp1252 quotes, hard-wrapped
lines). Fetching everything only fixes the first class, so the foundation is two pieces:

1. **Per-company coverage manifest.** *(Built: `code/providers/edgar_coverage.py`, `code/eval/coverage_manifest.py`,
   `code/eval/coverage_cohort.py`; first cohort run 2026-10-13 -- see the findings below.)* Enumerate every filing from the submissions metadata (incl.
   paginated `filings.files`) and record what Helix did with each: fetched / skipped + reason. Missing
   form families and date ranges then show up in a report instead of being found by hand. Metadata only,
   no bulk download. Prototype on Einride/Flipturn.
2. **Measured recall.** A list of known acquisitions from a source independent of Helix; report how many
   Helix finds. New misses add a row; fixes are proven against the list.

Only after both: a selective full-document loop over the form types the manifest shows are worth it.
Needs a networked machine (sec.gov is unreachable from the dev sandbox); the code and tests can be built
without it.

## Saturation study notes (frozen baseline -- annotate, do not edit results)

- **Trump Entertainment Resorts is a coverage test, not an extraction test.** Confirmed 2026-10-13 with the
  coverage manifest (`coverage_manifest.py --cik 943320`): CIK 0000943320 is the right entity, but all 662 of
  its filings fall between 1995-11-13 and 2013-03-20. It filed nothing in the 2015-2026 study window, so the
  2016 Icahn change of control (its only gold event) can never reach the extractor. The result file's
  `DISCLOSURE_NOT_IN_RETRIEVED_CORPUS` label is accurate. Keep this row out of any extraction-quality average.
  The baseline result is left untouched (frozen-baseline rule).
- **New test idea: buyer-side pivot.** A company that stops reporting is invisible to Helix by name; its
  acquisition is only findable in the *acquirer's* filings (here Icahn Enterprises L.P. -- look up and verify
  its CIK before use). Add as a separate new row, not a rewrite of the Trump row.
- **General lesson:** the manifest now flags `NO FILINGS IN WINDOW` (with earliest/latest dates) on the first run
  for any company in this state.

### First cohort run findings (2026-10-13, 12 companies, window 2015-2026)

Skipped deal-relevant forms, totals: 10-Q 315, DEFA14A 209, **425 76**, S-4 + S-4/A 27, 10-Q/A 4, SC TO-T(/A) 5.
- **Form 425 and S-4 are concentrated in the stock-merger companies** (425: Lumen 32, Intuitive Machines 21,
  Six Flags 13, Kraft Heinz 10; none elsewhere). Small volume, pre-closing signal -> first candidates for
  second-phase retrieval, together with F-4/DEFM14A.
- **10-Q (every company, ~35 each) and DEFA14A (routine proxy material) are high volume and likely low yield**
  -- deliberately not queued.
- **Unproven:** counts show where the forms are, not that they add events. Before building, run the extractor
  on a handful of 425/S-4 documents for Lumen, Six Flags, Kraft Heinz and see whether they surface events the
  gold lists miss.
- Einride AB (CIK 2095096): 79 filings, 12 retrievable (all 6-Ks, includes the Flipturn 6-K); 28 x 425 + F-4 + F-4/A
  appear to belong to its own listing transaction, not Flipturn (inferred from form types, unverified).

## EDGAR / foreign filers (from ADR-EDGAR-012 and its addendum)

| Item | Why parked | Pick up when |
|---|---|---|
| **6-K exhibit retrieval (EX-99.x press releases)** | Einride's 6-K body carried the deal summary, so not needed there. Many 6-Ks are stub covers that only say "see Exhibit 99.1" -- *frequency unmeasured*. | A sample of foreign-filer deal 6-Ks (run from a networked machine) shows stub bodies are common. Skip EX-2.1 (long contracts, names already in the body) unless bodies prove too thin. |
| **Gold entry `einride-1`** | Needs verbatim text already saved in `data/raw/einride/`. | Soon. Einride AB / Flipturn, Inc., AGREED_TO_ACQUIRE, agreement dated 2026-07-16. Do **not** label COMPLETED until a closing disclosure is found (Q3 2026 expected; a later 6-K). |
| **Closing check for Einride/Flipturn** | Only signing/announcement seen (6-K 2026-07-21). | Save the EX-99.1 press release or find the closing 6-K. |
| **8-K / 10-K hard-wrapped lines** | The source-line unwrap is gated to 6-K/20-F/40-F because 8-K `item_sections` keys on line-start headers and impact can't be measured offline. Likely affects some 8-Ks/10-Ks. | Networked cohort rerun can compare before/after; then consider enabling more broadly. |
| **Frozen-baseline cohort rerun (12 companies)** | The cp1252 decode fix touches every form (only filings that were not valid UTF-8). | From a networked machine, after current foundational work. |
| **Disk cache + rate limiter for retrieval** | Prolific 6-K filers mean many downloads; SEC limit ~10 req/s. | Before any bulk foreign-filer run. |
| **Second-phase forms** | 10-Q, S-4/F-4, 425, DEFM14A not retrieved. | After exhibit retrieval decision. |
| **Extractor noise** | Junk org `"Regulation S-K. The Company"` (sentence-boundary bleed from the Item 601(a)(5) footnote); stockholder-representative LLCs appear as org candidates; alias-less passages only get regex weight 0.5 < 1.5 threshold. | EVENT_GRAMMAR_MISS work. |
| **Lost-quote failure mode** | If quotes are lost (U+FFFD), the extractor can confidently pick the wrong counterparty (stockholder rep). Decode fix removes the production cause; a damaged copy can still trigger it. | Consider refusing/flagging text containing U+FFFD in alias-bearing passages. |

## State filings / identity (ADR-STATE-001/002)

- **DBA / `trade_names` on `EntityCandidate`** -- design only (ADR-STATE-002); consulted as fallback when `identity_key` resolution fails, not folded into `identity_key()`.
- **Shell recognition for reverse triangular mergers** in the Delaware Certificate of Merger extractor (currently yields sub -> target with no parent).
- **Wire `StateFilingProvider` into a CLI** and validate on a real Certificate of Merger.

## Other

- Newport News / TRW gold additions.
- Virtual analyst / semantic hypothesis layer (next milestone).
- M4.3A Sony confirmation run.
- Fix stale "sec 34.3" cross-reference in `ingest_supplied_evidence.py` (should point to `whois_parser.py` docstring).
- Clean up the two `EntityCandidate` classes (live `code/models/` package vs orphaned flat `code/models.py`).

## CrowdStrike audit follow-ups (ADR-EDGAR-013)
- Regex backend joins names across "and" (`Onum Technology Inc. and Pangea Cyber Corporation`), splitting the entity vote; fix by stopping the capture at a conjunction, not with a suffix list.
- Spaced/variant spellings (`Secure Circle, LLC` vs `SecureCircle`): consider pooling votes by identity rather than per surface spelling; the SecureCircle row still fails to recognise an entity.
- Gold hygiene: the Humio AGREED_TO_ACQUIRE duplicate row cannot be found in 10-Ks; decide whether announcement rows belong in 8-K/exhibit-only gold.
- Check the 2 unmatched CrowdStrike candidates and the 9 new cohort candidates against filings (likely real acquisitions missing from gold).
- Explain-miss: add a `--all` mode that loops gold rows so the shell loop is not needed.
