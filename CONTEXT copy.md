# Corporation Helix --- Project Context

**Last updated:** 2026-08-15\
**Current development target:** EDGAR v4 validation / Sony 20-F
ownership-table extraction

## 1. Project purpose

Corporation Helix is an evidence-driven corporate identity and
relationship resolver intended to fill a gap between corporate/M&A
intelligence and Attack Surface Management (ASM).

The MVP should answer questions such as:

-   What legal entities belong to a target company?
-   What subsidiaries, acquired companies, former names, brands, and
    related entities should security teams know about?
-   What evidence supports each relationship?
-   How confident should we be in a relationship?
-   Can the output later enrich ASM without incorrectly equating
    network/provider ownership with asset ownership?

The intended product is an **aggregator**, not a replacement for
commercial corporate-data vendors. Provider adapters should allow
customers to use sources they already license (for example Crunchbase,
Capital IQ, Refinitiv, etc.) alongside public sources.

The near-term goal is an MVP that can be demonstrated and then handed to
a development team.

## 2. Core architectural principle

Do not make the rest of the application understand provider-specific
quirks.

Target shape:

``` text
Corporate data providers
        |
        +-- SEC EDGAR
        +-- future licensed/commercial providers
        +-- future public/legal providers
        +-- customer-supplied data
        |
        v
Provider adapters
        |
        v
Canonical Evidence / Relationship Assertions
        |
        v
Normalization + Entity Resolution
        |
        v
Corporate Identity Graph
        |
        v
ASM / security / organizational consumers
```

EDGAR URLs, accession-number construction, filing types, exhibit
discovery, and parsing should ultimately remain inside the EDGAR
provider.

## 3. Important distinction for future ASM integration

Corporate ownership, infrastructure ownership, and asset operation are
different relationships.

The future model should be able to distinguish concepts such as:

``` text
CORPORATE_OWNS
SUBSIDIARY_OF
ACQUIRED_BY
OPERATED_BY

NETWORK_REGISTERED_TO
ASN_ANNOUNCED_BY
IP_ALLOCATED_TO

HOSTED_BY
CUSTOMER_OF
SERVICE_PROVIDER_FOR

DOMAIN_REGISTERED_TO
CERTIFICATE_OBSERVED_ON
```

This is especially important for telecom companies. An IP allocation or
ASN belonging to Lumen or Comcast does **not** automatically mean an
observed customer asset belongs in the telecom's ASM scope.

## 4. Benchmark / edge-case companies

The current benchmark deliberately contains companies that stress
different failure modes.

  ------------------------------------------------------------------------
  Company                 Purpose                  Current status
  ----------------------- ------------------------ -----------------------
  SentinelOne             Small, clean U.S.        PASS --- 10-K / EX-21
                          baseline                 

  Lumen Technologies      Large telecom;           PASS --- 10-K / EX-21
                          historical names and     extraction
                          provider/customer        
                          boundary                 

  Comcast                 Very large U.S.          PASS --- 10-K / EX-21
                          conglomerate / telecom / extraction
                          media                    

  Sony Group              Huge foreign private     20-F discovery PASS; v4
                          issuer; 20-F;            table-selection
                          significant-subsidiary   validation pending
                          disclosure               

  NTT DATA                Complex multinational    UNRESOLVED --- no
                          hierarchy / broader NTT  direct CIK found by
                          family / foreign entity  current SEC resolver
                          discovery                
  ------------------------------------------------------------------------

These are not meant to be special-cased in code. They are
acceptance/stress tests for generic provider behavior.

## 5. EDGAR implementation history

### Original / v1

The original EDGAR fetcher successfully worked against SentinelOne on
its first live run.

It uses SEC JSON resources to:

1.  Resolve a company to a CIK.
2.  Query SEC submissions.
3.  Locate a recent 10-K.
4.  Query the filing directory `index.json`.
5.  Locate an EX-21-like filename.
6.  Fetch the exhibit.
7.  Parse the HTML table into rows.
8.  Write raw JSON.

This means EDGAR navigation was already substantially less brittle than
originally feared. The main challenges are entity resolution,
filing-type differences, exhibit/table discovery, and normalization.

### v2 --- entity resolution

`fetch_edgar_v2.py` added conservative company resolution:

1.  Direct CIK
2.  Exact ticker
3.  Exact SEC legal title
4.  Exact normalized legal title
5.  Normalized substring fallback

It also:

-   strips common legal suffixes for comparison (`Corp`, `Corporation`,
    `Inc`, `Ltd`, etc.);
-   normalizes punctuation/case;
-   deduplicates SEC ticker records by CIK;
-   avoids fuzzy matching for now.

This fixed Sony name resolution and prevents Comcast's multiple tickers
for the same CIK from being treated as different corporations.

### v3 --- 20-F discovery

`fetch_edgar_v3.py` preserved the working 10-K / EX-21 path and added:

-   `20-F` / `20-F/A` discovery;
-   fetching the primary 20-F document;
-   scanning HTML tables for possible
    subsidiary/organizational-structure evidence;
-   `form_type` provenance;
-   `extraction_method` provenance;
-   candidate-table diagnostics.

Sony v3 successfully resolved:

``` text
Sony Group Corp
CIK 313838
20-F
filing date 2026-06-18
```

and proved that the foreign-filer discovery path works.

However, v3 selected too many tables and produced **498 extracted
rows**. The problem was not HTML extraction; it was table
classification.

### v4 --- current version

`fetch_edgar_v4.py` is the current development version.

The 10-K / EX-21 behavior is intentionally left unchanged.

For 20-Fs, v4:

-   scores tables based on structural ownership signals;
-   strongly rewards combinations of:
    -   company/subsidiary name,
    -   country/jurisdiction/incorporation,
    -   ownership percentage/voting/equity interest;
-   penalizes known false-positive table classes such as:
    -   corporate governance,
    -   directors/biographies,
    -   deferred tax,
    -   yield/interest-rate tables,
    -   remuneration,
    -   certification/exhibit material;
-   treats facility tables as enrichment rather than canonical ownership
    evidence;
-   selects a **single best ownership table** rather than concatenating
    every table above a loose threshold;
-   detects near-duplicate ownership tables and records them as
    duplicates.

**Current action:** run Sony against v4 and inspect
`edgar_sony_v4.json`.

Expected Sony result is roughly one header plus \~28
significant-subsidiary rows rather than 498 noisy rows.

## 6. Current observed EDGAR results

### SentinelOne

Known-good result:

``` text
31 extracted rows
10-K / Exhibit 21
CIK 1583708
```

The data is especially useful for normalization testing because it
contains:

-   current legal names;
-   former names, e.g. `Scalyr, LLC (fka Scalyr, Inc.)`;
-   status metadata such as `(Dormant)` and `(Non-operational)`;
-   countries;
-   relationship labels;
-   addresses;
-   at least one duplicate entity row in the filing.

Former-name and status parentheticals are **valuable metadata**, not
noise to discard.

### Lumen Technologies

Known result:

``` text
202 extracted rows before cleanup
10-K / Exhibit 21
CIK 18926
```

The filing exposes historically valuable corporate identities including
families such as:

-   CenturyTel / CenturyLink
-   Qwest
-   SAVVIS
-   Level 3
-   WilTel
-   Global Crossing
-   Broadwing
-   TelCove
-   Lumen

The parser also captures repeated table headers as rows, so
normalization/cleanup must remove those before treating every extracted
row as an entity.

Lumen is a future ASM attribution test because network
ownership/provider relationships must not be confused with customer
asset ownership.

### Comcast

Known result:

``` text
1,497 extracted rows
10-K / Exhibit 21
CIK 1166691
```

The result appears to represent a legitimately huge corporate footprint
rather than wholesale parser failure.

It includes corporate families/brands/entities associated with Comcast,
NBCUniversal, Universal, Sky, Telemundo, DreamWorks, Peacock, FreeWheel,
Masergy, Xfinity, Xumo, and others.

One observed cleanup example is an entity name with a leading `>`
character, which should be handled by normalization rather than
modifying raw evidence.

### Sony Group

v3 result:

``` text
498 extracted rows
20-F
CIK 313838
```

The v3 selector was too permissive.

Critically, the filing contains a strong canonical ownership table with
headers approximately:

``` text
Name of company
Country of incorporation / residence
(As of March 31, 2026) Percentage owned
```

This table contains roughly **28 significant subsidiaries**, generally
with ownership percentages.

Examples include:

-   Sony Interactive Entertainment Inc.
-   Sony Music Entertainment (Japan) Inc.
-   Sony Corporation
-   Sony Semiconductor Solutions Corporation
-   Sony Corporation of America
-   Sony Interactive Entertainment LLC
-   Sony Music Entertainment
-   Sony Music Publishing LLC
-   Sony Pictures Entertainment Inc.
-   Columbia Pictures Industries, Inc.
-   Sony Electronics Inc.
-   Sony Interactive Entertainment Europe Ltd.
-   Sony Europe B.V.
-   Sony Overseas Holding B.V.
-   Sony (China) Limited
-   Sony Electronics (Singapore) Pte. Ltd.

The 20-F also contains facility/business tables that may be useful
enrichment later, but they should not be confused with the canonical
ownership table.

Sony's evidence must be tagged as **significant-subsidiary coverage**,
not assumed to represent every Sony subsidiary.

### NTT DATA

Current resolver result:

``` text
No CIK found for 'ntt data'
```

This remains intentionally unresolved.

Do not force NTT DATA into a fuzzy or incorrect SEC match.

It should eventually test a separate capability:

``` text
NO_DIRECT_SEC_FILER
        |
        v
parent / related-company filing discovery
        |
        v
indirect evidence with appropriately lower/different provenance
```

## 7. Raw evidence vs normalized data

Never destructively "clean" the provider output.

Preserve raw source evidence and create normalized representations
downstream.

Example:

``` text
RAW:
Scalyr, LLC (fka Scalyr, Inc.)

NORMALIZED:
legal_name: Scalyr, LLC
former_names:
  - Scalyr, Inc.
```

Likewise:

``` text
RAW:
SentinelOne India Private Limited (Dormant)

NORMALIZED:
legal_name: SentinelOne India Private Limited
status: dormant
```

The raw evidence remains available for auditing.

## 8. Planned canonical foundation

Once EDGAR v4 passes Sony and regression tests, stop polishing the
scraper unless a material benchmark failure requires it.

The next engineering milestone is the provider/evidence foundation.

Proposed core objects:

``` text
EntityCandidate
RelationshipAssertion
Evidence
ProviderResult
```

and an abstraction similar to:

``` python
class CorporateDataProvider(Protocol):
    ...
```

Target usage:

``` python
result = provider.discover("SentinelOne")
```

Provider-specific behavior stays behind the adapter.

## 9. Evidence model requirements

Each relationship should eventually retain enough provenance to answer:

-   Who asserted this?
-   From which provider/source?
-   Which filing/document?
-   What filing date / effective date?
-   What extraction method?
-   Was it direct or indirect evidence?
-   What did the source actually claim?
-   Was the source complete or partial?
-   What normalization was applied?
-   What confidence do we assign after corroboration?

Example conceptual evidence:

``` json
{
  "source": "SEC_EDGAR",
  "form": "20-F",
  "relationship": "SUBSIDIARY_OF",
  "coverage": "significant_subsidiaries",
  "extraction_method": "20f_ownership_table",
  "as_of": "2026-03-31"
}
```

Do not infer that absence from a "significant subsidiaries" table means
the entity is not owned by the parent.

## 10. Ground-truth dataset

The existing SentinelOne ground-truth work is valuable but conceptually
mixes different classes of truth.

It should eventually be separated into categories such as:

``` text
positive_relationships
known_negatives
historical_relationships
unresolved
```

This matters because:

-   some entities are direct EDGAR evidence;
-   some were derived from OpenCorporates during development;
-   some are known acquisitions that occurred after a particular filing;
-   some are intentionally stored false positives.

Do not calculate benchmark accuracy as though all rows represent the
same assertion type or point in time.

## 11. OpenCorporates status

An OpenCorporates fetcher exists and is useful as prior development
work, but current licensing/terms make it unsuitable as a foundational
commercial MVP dependency without appropriate licensing.

Treat it as:

-   an optional future provider if properly licensed;
-   historical development/test material;
-   evidence that the provider-adapter model is useful.

Do not design the MVP around continued OpenCorporates access.

## 12. Other candidate providers

Potential future sources discussed include:

-   S&P Capital IQ
-   Refinitiv Workspace / SDC Platinum
-   Crunchbase
-   IMAA
-   GLEIF
-   customer-supplied/licensed corporate datasets

The product should be abstract enough that different customers can use
different subscriptions.

**Do not add providers merely to increase source count before the
canonical evidence/provider model exists.**

## 13. Current milestone order

### M0 --- benchmark and raw EDGAR acquisition

Status: **mostly complete**

-   [x] SentinelOne 10-K / EX-21
-   [x] Lumen 10-K / EX-21
-   [x] Comcast 10-K / EX-21
-   [x] Sony CIK resolution
-   [x] Sony 20-F discovery
-   [ ] Sony v4 ownership-table validation
-   [ ] SentinelOne v4 regression check
-   [ ] Optional Comcast/Lumen v4 regression check

### M1 --- provider + evidence foundation

Status: **next**

-   [ ] Define `EntityCandidate`
-   [ ] Define `RelationshipAssertion`
-   [ ] Define `Evidence`
-   [ ] Define `ProviderResult`
-   [ ] Define `CorporateDataProvider`
-   [ ] Wrap EDGAR implementation as `EdgarProvider`

### M2 --- normalization

Status: **not started**

-   [ ] legal-name normalization
-   [ ] former-name extraction
-   [ ] status extraction
-   [ ] jurisdiction normalization
-   [ ] ownership-percentage normalization
-   [ ] header/noise removal
-   [ ] duplicate-row handling
-   [ ] preserve raw evidence alongside normalized fields

### M3 --- entity resolution / corporate graph

Status: **not started**

-   [ ] resolve aliases/former names
-   [ ] direct vs indirect relationships
-   [ ] parent/subsidiary hierarchy
-   [ ] historical relationships
-   [ ] known negatives
-   [ ] confidence/corroboration
-   [ ] time-aware relationship state

### M4 --- second provider

Status: **deferred until canonical model exists**

Add one legally usable provider to prove the adapter architecture rather
than hard-coding EDGAR assumptions into the application.

### M5 --- ASM-oriented enrichment

Status: **future**

-   corporate identity → domain/asset suggestions;
-   provider/customer attribution;
-   network ownership vs asset operation;
-   ASN/RDAP/DNS/TLS/HTTP evidence;
-   security-team review workflow.

## 14. Immediate next commands

Current v4 Sony test:

``` bash
python3 ./code/fetch_edgar_v4.py \
  --company "Sony" \
  --out ./data/raw/edgar_sony_v4.json
```

Regression test:

``` bash
python3 ./code/fetch_edgar_v4.py \
  --company "SentinelOne" \
  --out ./data/raw/edgar_sentinelone_v4.json
```

Do **not** spend time rerunning NTT DATA with v4. Its failure is in
direct SEC entity discovery, not 20-F table selection.

## 15. Decision rules going forward

1.  **Benchmark before redesigning.**
2.  Turn observed failures into requirements rather than guessing at
    every edge case.
3.  Do not special-case benchmark companies.
4.  Preserve raw evidence.
5.  Keep provider-specific logic inside provider adapters.
6.  Distinguish source coverage from completeness.
7.  Do not equate corporate ownership with infrastructure ownership.
8.  Avoid fuzzy entity matching until conservative resolution is
    exhausted.
9.  Do not force a company into an incorrect SEC filer.
10. After Sony v4 passes, prioritize the canonical evidence model over
    further scraper polishing.

## 16. Current handoff point

If development resumes from this file, the immediate state is:

``` text
EDGAR v2
  entity resolution improved
        |
        v
EDGAR v3
  20-F discovery works
  Sony -> 498 rows (selector too broad)
        |
        v
EDGAR v4  <-- CURRENT
  structural ownership-table classifier
  single-best-table selection
  duplicate-table detection
        |
        v
RUN SONY V4
        |
        +-- clean (~29 rows) -> regression test -> canonical evidence model
        |
        +-- noisy/wrong       -> inspect diagnostics and make narrow classifier fix

NTT DATA remains a separate future entity-discovery problem.
```
