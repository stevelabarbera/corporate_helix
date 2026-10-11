# Helix backlog

Parked work, each with the trigger that put it here and the condition for picking it up.
Last updated 2026-10-11. Decisions live in the `DECISIONS_*.md` files; this is only the queue.

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
