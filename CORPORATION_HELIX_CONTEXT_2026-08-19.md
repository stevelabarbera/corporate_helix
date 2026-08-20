# Corporation Helix --- Project Context & Handoff

**Last updated:** 2026-08-19\
**Current milestone:** M3.8 --- temporal M&A event ingestion\
**Immediate benchmark:** Broadcom → VMware\
**Repository:** `corporate_helix`

> This file is the project handoff/source-of-truth document. It is
> intended to get a new engineer or a new AI session productive without
> reconstructing the project from chat history.

------------------------------------------------------------------------

## 1. The pitch

Corporation Helix is an evidence-driven corporate identity, ownership,
lineage, and M&A intelligence engine designed to solve a gap in Attack
Surface Management (ASM).

The problem is not merely finding a company's obvious legal
subsidiaries. Security teams need to know which subsidiaries,
acquisitions, former names, historical entities, brands, and related
organizations may still own or operate infrastructure that should be
investigated for ASM scope.

The intended differentiator is **auditable attribution rather than a
black-box score**:

1.  Per-entity and per-relationship provenance.
2.  Confidence based on agreement among structured signals, not string
    similarity alone.
3.  Conservative entity resolution designed to minimize false-positive
    ASM scope.
4.  Historical corporate lineage rather than only the current legal
    structure.
5.  A downstream path from corporate identity to infrastructure
    discovery.

The MVP is an **aggregator**, not a replacement for every corporate-data
vendor. Provider adapters should allow public sources and
customer-licensed sources to feed one canonical evidence model.

------------------------------------------------------------------------

## 2. Product question

The long-term system should be able to answer:

> **What organizations should be considered when investigating this
> company's attack surface today, including corporate history that
> current ownership records no longer make obvious?**

Examples include:

-   current subsidiaries;
-   acquired companies;
-   former legal names;
-   historical subsidiaries;
-   entities absorbed or converted during acquisitions;
-   brands and legacy organizations useful as infrastructure-discovery
    seeds;
-   candidate entities requiring analyst review.

A legal relationship does **not** automatically imply infrastructure
ownership.

------------------------------------------------------------------------

## 3. Architectural principles

### 3.1 Provider isolation

Provider-specific quirks stay inside adapters.

``` text
Corporate / legal / infrastructure data sources
        |
        +-- SEC EDGAR
        +-- GLEIF
        +-- RDAP / RIR
        +-- future public providers
        +-- future licensed providers
        +-- customer-supplied data
        |
        v
Provider adapters
        |
        v
Canonical Evidence / Assertions
        |
        v
Normalization
        |
        v
Candidate Generation + Entity Resolution
        |
        v
Corporate Identity + Temporal Event Graph
        |
        v
ASM / security / organizational consumers
```

### 3.2 Evidence is never destroyed

Raw provider evidence must be retained alongside normalized/canonical
data.

Normalization is additive and non-destructive.

LLM conclusions are **advice/metadata**, never source evidence.

### 3.3 False positives are expensive

Incorrectly pulling an unrelated company or infrastructure into ASM
scope is worse than temporarily leaving a legitimate entity unresolved.

Therefore:

-   fuzzy similarity alone never proves identity;
-   legal-form stripping alone never proves identity;
-   shared address alone never proves identity;
-   same parent alone does not mean two subsidiaries are the same legal
    entity;
-   LLM confidence alone never mutates the graph.

### 3.4 Relationship types must remain distinct

Corporate ownership and infrastructure attribution are different
concepts.

Future graph vocabulary should distinguish relationships such as:

``` text
SUBSIDIARY_OF
CORPORATE_OWNS
AGREED_TO_ACQUIRE
ACQUIRED
MERGED_INTO
CONVERTED_TO
RENAMED_TO

NETWORK_REGISTERED_TO
ASN_ANNOUNCED_BY
IP_ALLOCATED_TO
DOMAIN_REGISTERED_TO
CERTIFICATE_OBSERVED_ON

OPERATED_BY
HOSTED_BY
CUSTOMER_OF
SERVICE_PROVIDER_FOR
```

------------------------------------------------------------------------

## 4. Data-source strategy

### SEC EDGAR

Primary public corporate-structure and corporate-event source.

Implemented/validated paths:

-   10-K / Exhibit 21 subsidiary extraction;
-   20-F significant-subsidiary ownership-table extraction;
-   current M3.8 work: 8-K Item 1.01 / Item 2.01 temporal M&A event
    extraction.

Important limitation: Exhibit 21 is a significant-subsidiary disclosure,
not a complete ASM inventory.

### GLEIF

Important structured source for:

-   LEI identity;
-   Level 1 entity records;
-   Level 2 ownership relationships;
-   future ISO 20275 Entity Legal Form normalization.

GLEIF parsing work already exists and should eventually be joined into
the validated canonical/resolution pipeline.

### RDAP / RIR

RDAP parsing and conservative RDAP → GLEIF candidate ranking already
exist.

Long-term role: corporate identities and historical names become seeds
for infrastructure attribution rather than expecting SEC filings to
directly enumerate domains and IP ranges.

### OpenCorporates

Optional only. Licensing/acceptable-use constraints may not fit a
proprietary commercial MVP. Do not make the architecture dependent on
it.

### Future licensed/provider adapters

Potential examples:

-   S&P Capital IQ;
-   Refinitiv / SDC;
-   Crunchbase;
-   D&B;
-   Bureau van Dijk / Orbis;
-   customer-supplied corporate datasets.

------------------------------------------------------------------------

## 5. EDGAR extraction history

### v1 / v2 --- 10-K / Exhibit 21

Working extraction established against U.S. filers.

Observed examples:

-   **SentinelOne:** 31 extracted rows.
-   **Lumen Technologies:** 202 extracted rows before cleanup.
-   **Comcast:** 1,497 extracted rows.

v2 improved conservative SEC company/CIK resolution.

### v3 --- foreign filer / 20-F support

Sony successfully resolved and the 20-F path worked, but the initial
table scan selected too much:

``` text
Sony v3
1 filing
498 extracted rows
method: 20-F:20f_table_scan
```

### v4 --- structural ownership-table classifier

Sony was reduced from 498 noisy rows to the intended ownership table:

``` text
Sony v4
1 filing
29 extracted rows
method: 20-F:20f_ownership_table
```

This validated the strategy of selecting the strongest structural
ownership table rather than concatenating every superficially relevant
table.

------------------------------------------------------------------------

## 6. Canonical evidence and normalization

### M1 --- canonical evidence: VALIDATED

Different EDGAR structures now map into one evidence model while
retaining:

-   raw rows;
-   source/provider;
-   accession;
-   filing date;
-   filing type;
-   extraction method;
-   document provenance.

Core concepts include:

``` text
EntityCandidate
RelationshipAssertion
Evidence
ProviderResult
```

### M2 --- normalization: VALIDATED

Normalization is additive/non-destructive.

Validated examples include:

-   former names such as Scalyr;
-   status metadata;
-   jurisdiction;
-   deterministic entity/relationship keys;
-   duplicate handling.

Important unresolved normalization follow-up:

**International legal forms** such as:

``` text
B.V.
S.L.
s.r.o.
Sp. z o.o.
Pte. Ltd.
K.K.
G.K.
GmbH
S.A.
```

Do not solve this with an ever-growing hand-written suffix list. Loop
back using the **GLEIF ISO 20275 Entity Legal Forms (ELF)** data.

------------------------------------------------------------------------

## 7. Conservative entity resolution

### M3 --- VALIDATED

Canonical stored direction:

``` text
child --SUBSIDIARY_OF--> parent
```

Key behavior:

-   explicit root-company node;
-   exact identity merges only under strong structured agreement;
-   former-name continuity requires appropriate corroboration;
-   same-base-name candidates become review candidates rather than
    automatic merges;
-   cross-jurisdiction same-name entities are treated as distinct unless
    stronger continuity evidence overrides;
-   fuzzy similarity contributes evidence but is not authoritative.

Validated graph results:

### Sony

``` text
28 canonical subsidiary entities
28 relationships
resolved graph included root + subsidiaries
0 automatic merges
review case:
Sony Interactive Entertainment Inc. (JP)
vs
Sony Interactive Entertainment LLC (US)
```

### SentinelOne

``` text
21 graph nodes
20 relationships
0 automatic merges
1 review candidate:
Sentinel Labs Limited (GB)
vs
Sentinel Labs Pte Limited (SG)
```

------------------------------------------------------------------------

## 8. Resolution policy and tests

The resolver evolved into a hybrid rules/policy engine rather than one
hard-coded similarity formula.

Structured signals include:

-   normalized name;
-   legal-name base;
-   former names;
-   jurisdiction;
-   provider identifiers;
-   CIK / LEI / registration identifiers;
-   addresses;
-   explicit ownership/subsidiary evidence;
-   provider agreement;
-   fuzzy/name similarity.

Important rule:

``` text
same base name + different jurisdiction
!= same legal entity
```

unless stronger continuity/identifier evidence proves otherwise.

Current resolution regression suite:

``` text
PASS Sony cross-jurisdiction
PASS Sentinel Labs cross-jurisdiction
PASS Exact provider identifier
PASS Former-name continuity
PASS Ambiguous same-jurisdiction
PASS Explicit subsidiary

6 passed / 0 failed
```

------------------------------------------------------------------------

## 9. M3.5 / M3.6 --- evidence adjudication and LLM guardrails

Ambiguous candidates are converted into bounded evidence packets.

The LLM is not allowed to operate on the graph directly.

``` text
deterministic candidate
        |
        v
evidence packet
        |
        v
LLM advisory adjudication
        |
        v
semantic validation / guardrails
        |
        +-- VALID -> retain as model advice
        |
        +-- INVALID -> retain for audit; deterministic result remains
```

Current local Ollama environment has included:

``` text
gemma3:1b
qwen2:0.5b
all-minilm
nomic-embed-text
```

The development machine is resource-constrained, so avoid assuming large
local models.

### Guardrails implemented

The validator rejects model output that:

-   invents former-name continuity;
-   invents identifier matches;
-   invents shared-parent evidence;
-   contradicts jurisdiction signals;
-   claims a shared address when none exists;
-   cites unknown evidence IDs;
-   makes a conclusive decision without supporting evidence IDs;
-   returns `SAME_ENTITY / HIGH` without identity-grade evidence;
-   returns `DISTINCT_ENTITY / HIGH` without distinctness-grade
    evidence;
-   returns a decision whose rationale directly contradicts that
    decision.

Identity-grade evidence includes signals such as:

``` text
exact provider identifier
explicit former-name continuity
matching authoritative registration identifier
matching LEI / CIK
explicit legal-successor / continuity evidence
```

Distinctness-grade evidence includes signals such as:

``` text
conflicting authoritative identifiers
same legal-name base + jurisdiction conflict
separately enumerated entities in the same authoritative source
explicit distinct-entity evidence
```

Current tests:

``` text
semantic guardrails: 8 / 8
general guardrails:  4 / 4
resolution tests:    6 / 6
```

A key observed failure demonstrated why this architecture matters:

``` text
Gemma:
SAME_ENTITY / HIGH

Evidence:
no identity-grade signal

Validator:
INVALID

Graph action:
NONE
deterministic REVIEW remains
```

------------------------------------------------------------------------

## 10. M3.7 --- frozen evaluation baseline

A fixed synthetic evaluation corpus was created so model quality is
measured rather than tuned against one anecdote.

Eight cases:

1.  same entity via exact identifier;
2.  same entity via former-name continuity;
3.  distinct same-base entities across jurisdictions;
4.  ambiguous similar entities sharing an address;
5.  distinct entities with conflicting identifiers;
6.  same-parent but distinct subsidiaries;
7.  conflicting evidence;
8.  unrelated low-similarity entities.

### Deterministic baseline

``` text
PASS same_entity_exact_identifier
PASS same_entity_former_name
PASS distinct_cross_jurisdiction
PASS ambiguous_same_address
PASS distinct_identifier_conflict
PASS same_parent_distinct_entities
PASS conflicting_evidence
PASS unrelated_low_similarity

Deterministic corpus: 8 passed / 0 failed
```

### Gemma 3 1B baseline

``` text
same_entity_exact_identifier       PASS
same_entity_former_name            PASS
distinct_cross_jurisdiction        FAIL
ambiguous_same_address             FAIL / validator rejected
distinct_identifier_conflict       FAIL
same_parent_distinct_entities      FAIL
conflicting_evidence               FAIL / validator rejected
unrelated_low_similarity           FAIL

Ollama corpus: 2 passed / 6 failed
Validator: 6 valid / 2 invalid-or-error
```

**Decision:** freeze M3.7 baseline v1. Do not tune the benchmark to
improve Gemma's score.

Any future 2B/3B/local/remote model should be evaluated against the same
corpus.

### Resolver backlog item discovered by M3.7

The `conflicting_evidence` fixture currently deterministically returns
`ACCEPT` because a hard identity signal wins despite contradictory
evidence.

This behavior is currently expected by the frozen corpus, but should be
revisited:

> hard-confirm + meaningful contradictory evidence may deserve
> `REVIEW/CONFLICT` instead of unconditional `ACCEPT`.

Do not silently change this while working on M3.8.

------------------------------------------------------------------------

## 11. Why temporal M&A became the next priority

Current subsidiary lists are insufficient for ASM because infrastructure
often outlives corporate/legal structure.

A company acquired years ago may disappear from the current legal
hierarchy while domains, certificates, ASNs, registrations, software,
and forgotten systems still carry historical names.

Therefore Helix needs a **temporal corporate lineage graph**.

The desired progression is:

``` text
annual filings
10-K / 20-F / Exhibit 21
        |
        +--> structural baseline

8-K Item 1.01
        |
        +--> material agreement / announced transaction evidence

8-K Item 2.01
        |
        +--> completed acquisition/disposition evidence

later annual filings
        |
        +--> resulting legal structure
```

Example conceptual graph:

``` text
Broadcom
   |
   +-- AGREED_TO_ACQUIRE --> VMware
   |
   +-- ACQUIRED ----------> VMware
                              |
                              +-- historical VMware lineage
                                  +-- AirWatch
                                  +-- Nicira
                                  +-- VeloCloud
                                  +-- CloudHealth
                                  +-- Heptio
                                  +-- ...
```

Historical nodes should **not** simply disappear because a legal entity
was converted, renamed, merged, or absorbed.

------------------------------------------------------------------------

## 12. M3.8 --- CURRENT: EDGAR temporal M&A events

First benchmark:

**Broadcom → VMware**

Broadcom is valuable because its corporate lineage contains multiple
major acquisitions and legacy families, including VMware, CA
Technologies, Symantec Enterprise assets, and historical Avago/Broadcom
structure.

M3.8 introduces temporal event concepts:

``` text
AGREED_TO_ACQUIRE
ACQUIRED
MERGED_INTO
CONVERTED_TO
RENAMED_TO
M&A_CANDIDATE
```

New code:

``` text
code/fetch_edgar_events.py
code/canonicalize_edgar_events.py
```

Current M3.8 behavior:

-   discover 8-K / 8-K/A filings;
-   inspect Item 1.01 and Item 2.01;
-   extract relevant filing sections;
-   preserve SEC provenance;
-   emit conservative event candidates;
-   explicitly benchmark Broadcom/VMware;
-   unfamiliar M&A language becomes `M&A_CANDIDATE` rather than
    inventing transaction parties.

### Current command being run

``` bash
python3 ./code/fetch_edgar_events.py \
  --company "Broadcom" \
  --start 2022-01-01 \
  --end 2024-12-31 \
  --user-agent "CorporateHelix YOUR_EMAIL" \
  --out ./data/raw/edgar_broadcom_events.json
```

Then:

``` bash
python3 ./code/canonicalize_edgar_events.py \
  --in ./data/raw/edgar_broadcom_events.json \
  --out ./data/processed/canonical_broadcom_events.json
```

### Immediate checkpoint

Collect terminal output from **both** commands.

If filings are found but zero event candidates are emitted, inspect:

``` text
data/raw/edgar_broadcom_events.json
```

Do not prematurely generalize the parser. First learn the actual filing
structures.

------------------------------------------------------------------------

## 13. ASM expansion strategy

Do **not** expect EDGAR to directly enumerate the operational attack
surface.

Instead:

``` text
EDGAR / GLEIF / corporate providers
        |
        v
legal entity + relationship + historical lineage
        |
        v
identity seeds
  - current legal name
  - former names
  - acquired names
  - brands
  - CIK
  - LEI
  - registration numbers
  - addresses
        |
        v
infrastructure evidence providers
  - RDAP
  - RIR / ASN
  - WHOIS where legally/technically available
  - DNS
  - certificates / CT
  - domain observations
  - HTTP / technology fingerprints
        |
        v
ASM candidate assets
        |
        v
evidence scoring + analyst review
```

This separation is intentional.

Corporate lineage tells us **what names/entities to investigate**.

Infrastructure evidence tells us **whether an asset is actually
attributable**.

------------------------------------------------------------------------

## 14. Benchmark companies

Different companies stress different failure modes.

  ------------------------------------------------------------------------------
  Company                 Purpose / failure mode   Status
  ----------------------- ------------------------ -----------------------------
  SentinelOne             Small, hand-verifiable   Canonicalization/resolution
                          U.S. baseline; former    validated
                          names                    

  Sony                    Foreign filer, 20-F,     v4 extraction + resolution
                          international            validated
                          jurisdictions/legal      
                          forms                    

  Lumen                   Telecom, historical      Raw EDGAR extraction
                          identities,              validated; future ASM test
                          provider/customer        
                          boundary                 

  Comcast                 Huge conglomerate / very Raw EDGAR extraction
                          large subsidiary         validated
                          footprint                

  NTT DATA                Foreign/multinational    Direct SEC CIK discovery
                          entity-discovery problem unresolved

  Broadcom                Acquisition-heavy        **Current M3.8 benchmark**
                          temporal lineage         

  VMware                  Acquisition target with  **Current M3.8 lineage
                          rich legacy              benchmark**
                          subsidiary/acquisition   
                          history                  
  ------------------------------------------------------------------------------

Do not special-case benchmark companies in the final architecture.
Temporary benchmark-specific extraction is acceptable only to
learn/document filing patterns before generalization.

------------------------------------------------------------------------

## 15. Important parking-lot items

These are intentionally deferred, not forgotten:

-   international legal-form normalization using GLEIF ISO 20275 ELF;
-   broader fuzzy/similarity ensemble refinement;
-   blocking/indexing for large cross-provider entity sets;
-   join validated GLEIF Level 1/2 evidence into resolver;
-   join RDAP → GLEIF candidate ranking into the main graph pipeline;
-   multi-language legal-name matching;
-   second legally/commercially suitable provider adapter;
-   resolver behavior for hard-confirm + contradictory evidence;
-   stronger local model evaluation using frozen M3.7;
-   historical brands vs surviving legal entities;
-   domain/RIR/ASN/certificate expansion;
-   human-review workflow/UI;
-   point-in-time graph queries;
-   transaction announcement vs closing vs later legal restructuring.

------------------------------------------------------------------------

## 16. Rules we do not want to forget

1.  Preserve raw evidence.
2.  Provider-specific parsing stays in adapters.
3.  Never equate string similarity with identity.
4.  Never equate same address with identity.
5.  Never equate same parent with identity.
6.  Jurisdiction differences matter.
7.  Legal-form normalization is a comparison aid, not proof.
8.  Confidence is a function of structured signal agreement.
9.  LLM output is advisory and must survive deterministic validation.
10. Invalid LLM output never mutates the graph.
11. Do not tune frozen benchmarks to make a model look better.
12. Historical identities are valuable ASM seeds and should not simply
    disappear.
13. Corporate ownership != infrastructure ownership != asset operation.
14. Benchmark observed failures before redesigning.
15. Avoid benchmark-company special cases in the mature implementation.
16. False-positive ASM attribution is generally worse than conservative
    review.
17. Keep event dates and provenance so the graph can become
    point-in-time aware.

------------------------------------------------------------------------

## 17. Current project state in one diagram

``` text
M0 EDGAR acquisition
    VALIDATED
        |
        v
M1 Canonical evidence
    VALIDATED
        |
        v
M2 Normalization
    VALIDATED
        |
        v
M3 Conservative resolution
    VALIDATED
        |
        v
M3.5 Candidate scoring / policy engine
    VALIDATED
        |
        v
M3.6 Evidence packets + guarded LLM adjudication
    VALIDATED
        |
        v
M3.7 Fixed evaluation corpus
    BASELINE FROZEN
    deterministic 8/8
    Gemma 1B 2/8
        |
        v
M3.8 Temporal M&A event ingestion   <--- CURRENT
    Broadcom / VMware
        |
        v
Historical corporate lineage
        |
        v
ASM seed expansion
        |
        v
RDAP / RIR / ASN / DNS / TLS / domain evidence
        |
        v
Auditable ASM attribution
```

------------------------------------------------------------------------

## 18. How to resume after losing context

Read this entire file first.

Then inspect the repository and determine whether M3.8 Broadcom/VMware
output has already been produced.

If it has not:

``` bash
python3 ./code/fetch_edgar_events.py \
  --company "Broadcom" \
  --start 2022-01-01 \
  --end 2024-12-31 \
  --user-agent "CorporateHelix YOUR_EMAIL" \
  --out ./data/raw/edgar_broadcom_events.json

python3 ./code/canonicalize_edgar_events.py \
  --in ./data/raw/edgar_broadcom_events.json \
  --out ./data/processed/canonical_broadcom_events.json
```

If it has, inspect:

``` text
data/raw/edgar_broadcom_events.json
data/processed/canonical_broadcom_events.json
```

and continue from the observed Broadcom/VMware event structures.

Before making unrelated resolver changes, remember:

``` text
M3.7 deterministic baseline = 8/8
M3.7 Gemma 3 1B baseline    = 2/8
```

Those results are intentionally frozen.

------------------------------------------------------------------------

## 19. Immediate next decision after M3.8 output

The next implementation decision should be based on the real Broadcom
output:

``` text
A. Correct Item 1.01 / 2.01 events found
   -> generalize party/event extraction

B. Correct filings found but events missed
   -> inspect raw filing structure and make a narrow parser improvement

C. Wrong/no filings discovered
   -> fix filing discovery before touching event extraction

D. Good event extraction
   -> attach canonical events to temporal graph nodes and begin historical
      VMware lineage expansion
```

Do not skip directly to infrastructure discovery until the temporal
corporate-event model is credible.
