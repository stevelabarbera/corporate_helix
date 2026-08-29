# Corporation Helix --- Project Context & Handoff

**Last updated:** 2026-08-28\
**Current milestone:** M4.2 --- GLEIF Level 2 → Level 1 identity
enrichment\
**Immediate benchmark:** real GLEIF RR relationship → local LEI index →
canonical graph → ASM seed\
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

  ----------------------------------------------------------------------------
  Company               Purpose / failure mode   Status
  --------------------- ------------------------ -----------------------------
  SentinelOne           Small, hand-verifiable   Canonicalization/resolution
                        U.S. baseline; former    validated
                        names                    

  Sony                  Foreign filer, 20-F,     v4 extraction + resolution
                        international            validated
                        jurisdictions/legal      
                        forms                    

  Lumen                 Telecom, historical      Raw EDGAR extraction
                        identities,              validated; future ASM test
                        provider/customer        
                        boundary                 

  Comcast               Huge conglomerate / very Raw EDGAR extraction
                        large subsidiary         validated
                        footprint                

  NTT DATA              Foreign/multinational    Direct SEC CIK discovery
                        entity-discovery problem unresolved

  Broadcom              Acquisition-heavy        **Current M3.8 benchmark**
                        temporal lineage         

  VMware                Acquisition target with  **Current M3.8 lineage
                        rich legacy              benchmark**
                        subsidiary/acquisition   
                        history                  
  ----------------------------------------------------------------------------

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
corporate-event model is credible. ---

# 20. 2026-08-28 CURRENT-STATE OVERRIDE

> **This section is authoritative when it conflicts with older
> milestone/status text elsewhere in this historical handoff.** Older
> sections are retained because they document validated behavior, design
> decisions, benchmarks, and why the project evolved.

## 20.1 Strategic decision

The active MVP path is now:

``` text
structured corporate sources
        |
        v
canonical evidence
        |
        v
temporal corporate graph
        |
        v
candidate corporate identity seeds
        |
        v
infrastructure evidence / ASM attribution
```

The legal-document/event-extraction work remains valuable, but it is
**not on the MVP critical path**.

The broader approximately 100-company legal-event generalization /
source-yield study is **PARKED** until structured providers are
operational enough to answer the more useful question:

> What unique candidate-ASM-seed recall does legal-document parsing add
> beyond structured providers, and what review/false-positive cost does
> that incremental yield create?

Do not restart the broad legal research merely because it is available.
Restart it when legal parsing becomes a demonstrated recall bottleneck
or when a structured-vs-legal source-yield comparison is the next
product question.

## 20.2 Legal-event extraction status

The M3.8/M3.9 event-extraction branch is preserved as a working/frozen
capability:

-   `code/fetch_edgar_events.py` generalized beyond hardcoded
    Broadcom/VMware logic.
-   `code/canonicalize_edgar_events.py` preserves candidate parties.
-   `code/generate_event_report.py` produces a Markdown timeline/report.
-   `code/test_event_extraction.py` has 11 regression checks.
-   Broadcom/VMware acquisition events were extracted successfully.
-   Comcast produced a correct financing/non-M&A true negative.
-   Lumen produced real divestiture candidates.
-   Ambiguous divestiture buyers deliberately remain
    `M&A_CANDIDATE / REVIEW` rather than asserting a plausible-but-wrong
    buyer.

This is a **safety feature**, not an unfinished bug to bypass.

## 20.3 Repository recovery / stabilization

Repository trouble exposed multiple generations of code:

-   the current repository primarily uses `code/`;
-   an older recovered `src.zip` contained useful earlier GLEIF work;
-   old tests/imports referencing `src...` explain some historical
    inconsistencies;
-   selected recovered utilities were copied into `code/` for
    evaluation;
-   recovered code is a **salvage branch**, not a second architecture.

Recovered useful GLEIF behavior includes:

-   rich Level 1 entity parsing;
-   transliterated names/addresses;
-   registration and validation metadata;
-   legal-entity events and successor identities;
-   Level 2 relationship parsing;
-   memory-safe `ijson` streaming of multi-GB Golden Copies.

Rule going forward:

> Reconcile by responsibility. Pick one implementation as the winner,
> preserve useful tested behavior, and remove/retire duplicates. Do not
> maintain parallel `src/`, `code/`, and experimental GLEIF pipelines.

### Repository stabilization acceptance test

A fresh checkout should eventually support:

``` text
git clone
→ create/activate venv
→ install dependencies
→ run regression tests
→ run a known GLEIF fixture
→ reproduce the expected graph + candidate seed
```

without requiring chat history or knowledge of recovered ZIP files.

## 20.4 GLEIF Level 1 index --- VALIDATED

A streaming SQLite indexer now successfully processes the full local
GLEIF Level 1 Golden Copy.

Current tool:

``` text
code/build_gleif_lei_index.py
```

Current database:

``` text
data/processed/gleif_lei.sqlite
```

Validated full build:

``` text
input snapshot: 20260804-0800-gleif-goldencopy-lei2-golden-copy.json
scanned:        3,393,123
indexed:        3,393,123
skipped:        0
runtime:        186.1 seconds
known repairs:  1
```

The source JSON contained one reproducible syntax defect near byte
`4,666,189,837`:

``` text
},.
```

The indexer now narrowly repairs only the known exact malformed
sequence:

``` text
b'},.' -> b'},'
```

and records/logs the repair. Other malformed JSON is not silently
generalized away.


### Known upstream GLEIF Golden Copy parsing issue

This malformed sequence has caused repeated confusion during development, so
treat it as a documented upstream-data-quality issue rather than assuming an
`ijson`, SQLite, Unicode, buffering, or local-environment failure.

Observed behavior:

``` text
parser fails reproducibly at approximately record 1,177,704
buffered file position reported near 4.666 GB
exact malformed bytes found near absolute offset 4,666,189,837
invalid JSON sequence: },.
```

The failure was deterministic across repeated reads of the same Golden Copy,
and raw-byte inspection confirmed that the extra period was physically present
in the downloaded JSON.

Operational rule for future GLEIF snapshots:

1. If a full Golden Copy fails parsing, first check whether the failure is the
   same known `},.` defect before redesigning the importer.
2. Keep the repair intentionally narrow and logged; do not create a permissive
   "fix arbitrary JSON" layer.
3. Record the snapshot filename/date and repair count in index metadata.
4. Periodically test newer GLEIF Golden Copies without the repair. GLEIF may
   correct the upstream generator/data record in later snapshots.
5. Do **not** remove the defensive repair merely because one newer snapshot is
   clean. Retire it only after repeated clean snapshots, or keep it as a
   narrowly-scoped compatibility guard for historical files.

Expected long-term outcome: this defect will likely disappear from newer
upstream snapshots once the malformed source record or generation path is
corrected. Helix should still remain defensive because historical Golden Copies
may continue to contain it.

The index includes useful lookup fields such as:

-   LEI;
-   legal name and normalized legal name;
-   legal jurisdiction;
-   entity status/category;
-   legal-form fields;
-   legal/HQ geography;
-   registration status;
-   registration/update dates;
-   managing LOU;
-   validation sources.

### Level 1 lookup proof

Two LEIs from the real Level 2 relationship proof resolve correctly:

``` text
010PWNH4K3BLIC3I7R03
  GESTION PLACEMENTS DESJARDINS INC.
  CA-QC
  entity_status=ACTIVE
  registration_status=LAPSED

549300COKYB5EGSU1838
  Desjardins Holding financier inc.
  CA-QC
  entity_status=ACTIVE
  registration_status=ISSUED
```

This validates the local Level 1 identity lookup needed to enrich Level
2 relationship endpoints.

## 20.5 GLEIF Level 2 RR vertical slice --- VALIDATED

Real uploaded RR Golden Copy:

``` text
20260817-0800-gleif-goldencopy-rr-golden-copy.json.zip
```

Inner JSON is approximately 1.1 GB and uses top-level `relations`.

Observed relationship types include:

``` text
IS_FUND-MANAGED_BY
IS_ULTIMATELY_CONSOLIDATED_BY
IS_DIRECTLY_CONSOLIDATED_BY
IS_SUBFUND_OF
IS_INTERNATIONAL_BRANCH_OF
IS_FEEDER_TO
```

Initial MVP support is deliberately limited to accounting-consolidation
relationships. Do not conflate fund management, branch, subfund, feeder,
or other relationship semantics with ownership.

Current mapping:

``` text
IS_DIRECTLY_CONSOLIDATED_BY
    -> DIRECT_ACCOUNTING_PARENT

IS_ULTIMATELY_CONSOLIDATED_BY
    -> ULTIMATE_ACCOUNTING_PARENT
```

The RR adapter treats:

``` text
StartNode = child
EndNode   = accounting parent
```

and preserves raw relationship evidence, relationship status/periods, RR
registration metadata, validation metadata, and provenance.

### Real relationship proof

Validated real edge:

``` text
GESTION PLACEMENTS DESJARDINS INC.
  LEI 010PWNH4K3BLIC3I7R03
        |
        | DIRECT_ACCOUNTING_PARENT
        v
Desjardins Holding financier inc.
  LEI 549300COKYB5EGSU1838
```

The proof pipeline produced:

``` text
2 graph nodes
1 relationship
0 merges
0 review candidates
1 related-legal-entity ASM candidate seed
```

The generated seed correctly identifies the **non-root endpoint** as the
new candidate. This fixed an earlier directional assumption that always
treated the child endpoint as the interesting seed.

Critical rule:

> Corporate relationship confidence can be HIGH while infrastructure
> attribution confidence remains UNKNOWN. Never auto-attribute
> infrastructure merely because a corporate edge exists.

## 20.6 Resolver compatibility fix

The resolver previously assumed the subject of the first relationship
was the queried/root company. That assumption happened to fit the EDGAR
shape but is wrong for GLEIF child → parent relationships.

Root identity is now derived from the provider's resolved entity/name
rather than relationship direction.

Regression check against SentinelOne remained unchanged:

``` text
21 nodes
20 relationships
0 merges
1 review candidate
```

so the GLEIF correction did not alter the established SentinelOne graph
counts.

------------------------------------------------------------------------

# 21. ACTIVE ROADMAP

The roadmap is dependency-aware so a blocked task does not block
productive work.

  --------------------------------------------------------------------------------
  Milestone         Objective                  Dependency        Status
  ----------------- -------------------------- ----------------- -----------------
  **M0.5**          Repository stabilization / None              **ACTIVE
                    single source of truth                       SUPPORTING**

  **M4.1**          Full GLEIF Level 1 local   None              **COMPLETE**
                    identity index                               

  **M4.2**          Automatic Level 2 RR →     M4.1              **NEXT**
                    Level 1 identity                             
                    enrichment                                   

  **M4.3**          Arbitrary GLEIF RR →       M4.2              UPCOMING
                    canonical graph → ASM seed                   

  **M4.4**          GLEIF temporal/history     M4.2              PARALLELIZABLE
                    handling                                     

  **M4.5**          Reporting exceptions +     M4.2              PARALLELIZABLE
                    relationship semantics                       

  **M4.6**          GLEIF source-yield         M4.3              UPCOMING
                    benchmark/scorecard                          

  **M5.0**          Select/integrate second    M4.6 ideally      RESEARCH CAN
                    structured provider                          PARALLELIZE

  **M5.1**          Cross-provider             M5.0              UPCOMING
                    resolution/deduplication                     

  **M5.2**          Multi-source confidence +  M5.1              UPCOMING
                    provenance                                   

  **M6.0**          Formal ASM seed            M4.3              CAN START EARLY
                    handoff/schema                               

  **M6.1**          Seed safety/disposition    M6.0              UPCOMING
                    policy                                       

  **M6.2**          Human/customer REVIEW      M6.1              LATER
                    workflow                                     

  **M3.9-R**        \~100-company legal-source Independent       **PARKED**
                    generalization/yield study                   
  --------------------------------------------------------------------------------

## 21.1 M4.2 --- NEXT

Wire:

``` text
data/processed/gleif_lei.sqlite
```

directly into the Level 2 RR canonicalization path.

Desired helper:

``` text
lookup_lei(db_path, lei) -> dict | None
```

Desired CLI/API behavior:

``` text
--lei-index data/processed/gleif_lei.sqlite
```

The RR pipeline should no longer require manual:

``` text
--child-name
--child-jurisdiction
--parent-name
--parent-jurisdiction
```

for normal operation.

Acceptance test:

``` text
raw RR record
→ child + parent LEIs
→ automatic SQLite identity enrichment
→ canonical evidence
→ resolver
→ graph
→ correctly directed candidate ASM seed
```

with no web/manual name enrichment.

## 21.2 M4.3 --- full reusable GLEIF vertical slice

After M4.2, prove the same path works for arbitrary supported RR records
rather than one hand-selected example.

Required properties:

-   Level 1 identity attached to both endpoints when available;
-   missing Level 1 identity handled conservatively;
-   raw RR evidence retained;
-   relationship semantics retained;
-   dates/status retained;
-   canonical graph generated;
-   root-aware candidate seed generated;
-   no corporate edge directly authorizes infrastructure scope.

## 21.3 M4.4 --- temporal GLEIF relationships

Preserve and expose:

-   relationship start/end periods;
-   accounting periods;
-   active/inactive relationship status;
-   Level 1 entity events;
-   successors/former identities where available.

Goal: Helix should eventually answer not just **who is related**, but
**when**, without deleting historically useful ASM seeds.

## 21.4 M4.5 --- semantics and exceptions

Explicitly model rather than flatten:

-   direct accounting parent;
-   ultimate accounting parent;
-   reporting exceptions such as `NO_KNOWN_PERSON`;
-   unsupported relationship classes;
-   relationship-record registration state vs corporate relationship
    state.

Unsupported semantics should be preserved for later analysis, not
silently converted into ownership.

## 21.5 M4.6 --- source-yield scorecard

Measure whether a provider is worth its complexity.

Per company/source, capture at least:

``` text
entities discovered
relationships discovered
candidate ASM seeds
unique seeds not supplied by other sources
SAFE/AUTO candidates
REVIEW candidates
rejected candidates
known unsafe false positives
runtime
provenance completeness
```

The optimization target is **incremental useful ASM seed yield**, not
raw record count or parser sophistication.

## 21.6 M5 --- next provider

Do not choose the next provider merely because it has an API.

Choose based on expected **incremental** coverage after GLEIF:

-   legal entities without LEIs;
-   acquisitions/history GLEIF misses;
-   brands/former identities;
-   useful identifiers for downstream infrastructure discovery;
-   licensing/commercial suitability;
-   provenance quality;
-   review burden.

Potential candidates remain provider/customer dependent; architecture
must continue to isolate provider-specific quirks in adapters.

## 21.7 M6 --- ASM handoff

Formalize the boundary between corporate intelligence and infrastructure
attribution.

A corporate seed should carry enough context to investigate:

``` text
canonical entity/name
aliases/former names
LEI / CIK / registration IDs
jurisdiction
relationship to root
relationship dates/status
source/provenance
corporate confidence
infrastructure attribution confidence
disposition / review requirement
```

Corporate lineage says **what to investigate**. Infrastructure evidence
says **what assets can actually be attributed**.

------------------------------------------------------------------------

# 22. WHAT SHOULD I WORK ON?

Use this instead of inventing a new task when a session starts.

``` text
START
  |
  +-- Is the repository reproducible / are tests runnable?
  |      NO -> M0.5 repository stabilization
  |      YES
  |
  +-- Does RR automatically enrich both LEIs from gleif_lei.sqlite?
  |      NO -> M4.2  <--- CURRENT NEXT TASK
  |      YES
  |
  +-- Can arbitrary supported RR records produce a canonical graph + seed?
  |      NO -> M4.3
  |      YES
  |
  +-- Are relationship dates/status/exceptions represented correctly?
  |      NO -> M4.4 / M4.5
  |      YES
  |
  +-- Have we measured GLEIF's real candidate-seed yield?
  |      NO -> M4.6
  |      YES
  |
  +-- Select next structured provider based on incremental yield
  |      -> M5
  |
  +-- Formalize/expand downstream ASM handoff and review policy
         -> M6
```

## 22.1 If the primary task is blocked

Do **not** create a new rabbit hole. Choose one of these bounded
alternatives:

1.  **Repository stabilization**
    -   remove/retire duplicate recovered implementations;
    -   fix package/import layout;
    -   lock dependencies;
    -   make a clean regression command;
    -   document fixture commands.
2.  **GLEIF semantics/tests**
    -   add fixtures for direct vs ultimate accounting parent;
    -   add reporting-exception fixtures;
    -   add missing-Level-1 endpoint behavior;
    -   verify inactive/lapsed relationship-record handling.
3.  **ASM seed contract**
    -   define seed JSON/schema;
    -   define SAFE/AUTO vs REVIEW vs REJECT semantics;
    -   ensure corporate confidence and infrastructure confidence remain
        separate.
4.  **Source-yield instrumentation**
    -   implement counters/metrics before broad provider benchmarking.
5.  **Next-provider research**
    -   compare commercial/legal suitability and expected incremental
        coverage;
    -   do not integrate until there is a reason it should beat/add to
        GLEIF.
6.  **Documentation**
    -   update this file;
    -   record exact commands and expected outputs;
    -   capture decisions before changing architecture.

The parked 100-company legal study is **not** the default fallback task.

------------------------------------------------------------------------

# 23. DOCUMENT CONSOLIDATION / SOURCE OF TRUTH

The repository accumulated overlapping context files. Going forward:

## Canonical

**This document is the single durable project handoff/source of truth.**

It contains:

-   product intent;
-   architectural rules;
-   validated milestones;
-   frozen benchmarks;
-   current status;
-   roadmap;
-   blocked-work alternatives;
-   session-resume instructions.

## Supporting only

`ROADMAP.md` may remain **only if it is intentionally kept as a short,
generated/curated dashboard**. It must not contain independent project
truth that can drift from this document.

## Archive

`CONTEXT_EVENT_EXTRACTION.md` should be treated as a historical
sub-thread snapshot. Its valuable decisions are summarized here. Keep it
for audit/history if desired, but do not use it to determine the current
milestone.

The older short `CONTEXT.md` is superseded by this document. Archive or
remove it after confirming no unique information is missing.

Avoid creating new dated context files for every session. Update this
canonical handoff and let Git history provide the date-by-date archive.

------------------------------------------------------------------------

# 24. START HERE NEXT SESSION

1.  Read **Sections 20--24 first**. Read older sections only when
    historical detail is needed.
2.  Activate the project virtual environment.
3.  Confirm the Level 1 SQLite index exists:

``` text
data/processed/gleif_lei.sqlite
```

4.  Current next engineering task:

> **M4.2 --- make the RR adapter/canonicalizer enrich child and parent
> LEIs automatically from the SQLite Level 1 index.**

5.  Preserve these non-negotiable rules while implementing it:

``` text
raw evidence is retained
provider quirks stay in adapters
relationship direction is semantic, not assumed from root position
historical dates/status are preserved
corporate relationship confidence != infrastructure attribution confidence
false-positive ASM attribution is worse than conservative REVIEW/UNKNOWN
```

6.  Once M4.2 passes, immediately proceed to M4.3 rather than reopening
    legal parser research.

## Known-good Level 1 verification query

``` bash
sqlite3 -header -column data/processed/gleif_lei.sqlite "
SELECT
    lei,
    legal_name,
    legal_jurisdiction,
    entity_status,
    registration_status
FROM lei_entities
WHERE lei IN (
    '010PWNH4K3BLIC3I7R03',
    '549300COKYB5EGSU1838'
);
"
```

Expected identities:

``` text
010PWNH4K3BLIC3I7R03  GESTION PLACEMENTS DESJARDINS INC.  CA-QC
549300COKYB5EGSU1838  Desjardins Holding financier inc.   CA-QC
```

If those resolve, the Level 1 prerequisite for M4.2 is healthy.

------------------------------------------------------------------------

# 25. CURRENT STATUS --- ONE SCREEN

``` text
Corporation Helix
=================

Foundation
  M0   EDGAR acquisition                         VALIDATED
  M1   Canonical evidence                        VALIDATED
  M2   Normalization                             VALIDATED
  M3   Conservative resolution                   VALIDATED
  M3.5 Candidate policy/scoring                  VALIDATED
  M3.6 Guarded LLM adjudication                  VALIDATED
  M3.7 Frozen eval corpus                        VALIDATED / FROZEN
  M3.8/3.9 legal event extraction                WORKING / PARKED FROM MVP PATH

GLEIF structured-source path
  M4.1 Full Level 1 SQLite identity index        COMPLETE
       3,393,123 / 3,393,123 indexed
       0 skipped
       1 narrow source-syntax repair
  M4.2 RR -> automatic Level 1 enrichment        NEXT
  M4.3 RR -> canonical graph -> ASM seed         UPCOMING
  M4.4 temporal GLEIF handling                   UPCOMING
  M4.5 semantics/reporting exceptions            UPCOMING
  M4.6 source-yield benchmark                    UPCOMING

Expansion
  M5   second structured provider                LATER
  M6   formal ASM seed/review handoff            LATER

Repository
  M0.5 single-source/reproducibility cleanup     ACTIVE SUPPORTING

Research
  ~100-company legal generalization/yield study  PARKED
```


---

# 26. INTERNAL ASM OPERATOR CLI — EARLY OPERATIONALIZATION

## 26.1 Why this moves forward now

Corporation Helix should begin producing useful operator output before the
research architecture is "finished."

A likely near-term real-world use case is configuring customer ASM instances.
That workflow requires discovering corporate names, subsidiaries, former
identities, acquisitions, and related legal entities that should be investigated
as potential ASM seeds. Historically this has required manual Google searches
for mergers/acquisitions and hand-built company-name lists.

Helix can now begin replacing part of that manual workflow.

This is not a customer-facing product milestone yet. The first goal is an
**internal operator tool that saves analyst time and creates real validation
data for Helix.**

## 26.2 New operational target — M4.3A

Target command:

```bash
python code/helix_company.py --company "Sony"
```

Initial output should organize candidate identities by why they were returned,
rather than flattening every name into the word "alias."

Useful categories include:

```text
CURRENT_LEGAL_NAME
FORMER_NAME
SUBSIDIARY
DIRECT_ACCOUNTING_PARENT
ULTIMATE_ACCOUNTING_PARENT
ACQUIRED_ENTITY
SUCCESSOR
BRAND
RELATED_LEGAL_ENTITY
REVIEW
```

Each result should retain, when available:

```text
name
LEI / CIK / registration identifier
jurisdiction
relationship to root
relationship dates/status
source/provider
provenance
corporate confidence
infrastructure attribution confidence
disposition / review reason
```

The operator should be able to distinguish a true alias/former name from a
separate related legal entity even though both may be useful ASM investigation
seeds.

## 26.3 Level 2 relationship index — M4.2B

Do not scan the approximately 1.1 GB RR Golden Copy for every company query.

Build a persistent local relationship index, likely SQLite, supporting fast
lookup in both directions:

```text
child LEI  -> relationship -> parent LEI
parent LEI -> relationship -> child LEIs
```

Candidate fields:

```text
child_lei
parent_lei
relationship_type
relationship_status
relationship_start
relationship_end
registration_status
validation metadata
source/provenance reference
```

Indexes should at minimum support fast lookup by `child_lei` and `parent_lei`.

This combines with the existing Level 1 identity database to provide:

```text
company-name search
    -> candidate root LEI
    -> relationship lookup
    -> related LEIs
    -> Level 1 identity enrichment
    -> canonical graph
    -> operator ASM seed list
```

## 26.4 Root ambiguity is expected

A company-name query may match multiple legitimate entities.

The first internal CLI may simply display candidates and ask the operator to
select the intended root:

```text
Multiple root candidates for "Sony":

1. <candidate>
2. <candidate>
3. <candidate>

Choose root:
```

Do not silently choose a similarly named entity when structured evidence is
ambiguous.

## 26.5 Missing Level 1 endpoint policy — EXPLICIT DECISION

A valid RR relationship must not disappear merely because `lookup_lei()` cannot
enrich one endpoint from the local Level 1 index.

Chosen behavior:

> Preserve the RR relationship and the unresolved endpoint using its bare LEI,
> mark enrichment incomplete, and force conservative REVIEW/UNKNOWN behavior.
> Never invent the missing legal name or silently discard the relationship.

Suggested states:

```text
RESOLVED
UNRESOLVED_LEVEL1
PARTIAL_ENRICHMENT
```

Required cases:

1. **Both endpoints resolve**
   - normal canonical graph edge;
   - normal candidate-seed policy.

2. **One endpoint does not resolve**
   - preserve raw RR evidence;
   - preserve relationship edge;
   - create unresolved endpoint using bare LEI;
   - mark partial enrichment;
   - REVIEW/UNKNOWN rather than automatic attribution.

3. **Neither endpoint resolves**
   - preserve raw RR evidence;
   - preserve bare LEI endpoints and relationship;
   - no automatic ASM expansion beyond what the evidence supports.

Important distinction:

> Missing Level 1 enrichment does not invalidate an otherwise valid GLEIF RR
> assertion. It limits what Helix knows about an endpoint.

## 26.6 Source layering

The first operator CLI should work from GLEIF without requiring EDGAR success.

Then layer existing sources:

```text
                     company query
                          |
             +------------+------------+
             |                         |
           GLEIF                     EDGAR
             |                         |
   structured identities/       subsidiaries/events/
      relationships              historical identities
             |                         |
             +------------+------------+
                          |
                   canonical resolve
                          |
                          v
                ASM investigation seeds
```

GLEIF is the initial structured foundation.

EDGAR should add useful coverage where available rather than becoming a hard
dependency for every company.

Later providers should follow the same adapter/canonical model.

## 26.7 Real customer onboarding becomes a validation corpus

Real ASM onboarding should double as product validation.

For each company, retain lightweight metrics such as:

```text
GLEIF seeds discovered
EDGAR seeds added
other-provider seeds added
manual-research discoveries Helix missed
duplicates removed
REVIEW candidates
rejected candidates
known false positives
```

Most importantly, record **manual discoveries Helix missed**.

Example conceptual scorecard:

```text
Customer / Company A
  GLEIF discovered:        21
  EDGAR uniquely added:     8
  manual research added:    6
  false positives:          1

Customer / Company B
  GLEIF discovered:         3
  EDGAR uniquely added:    14
  manual research added:   19
```

This evidence should drive source and feature prioritization.

If repeated customer onboarding shows that manual M&A research finds many
valuable historical identities absent from structured providers, that becomes
evidence to resume/invest further in the parked legal-event/generalization work.

## 26.8 Revised near-term execution order

```text
M4.1   Full Level 1 identity index
       COMPLETE
          |
          v
M4.2   Automatic RR endpoint -> Level 1 enrichment
       NEXT
          |
          v
M4.2B  Persistent Level 2 relationship index
          |
          v
M4.3A  Internal helix_company.py operator CLI
          |
          +--> GLEIF company expansion
          +--> root selection
          +--> relationship reasons/provenance
          +--> REVIEW handling
          +--> text/JSON/CSV output
          |
          v
       Use on real ASM onboarding
          |
          v
       Record manual misses + false positives
          |
          v
M4.3/M4.6 harden graph + measure source yield
          |
          v
M5     Choose next provider from observed gaps
```

The operator CLI is now the practical target that drives M4.2/M4.3 rather than
waiting until every research milestone is complete.

## 26.9 First-version scope discipline

For the first internal version:

**Build:**
- company-name lookup;
- root selection when ambiguous;
- GLEIF Level 1 + supported Level 2 expansion;
- canonical relationship labels;
- provenance;
- REVIEW/UNKNOWN behavior;
- readable terminal output;
- JSON/CSV export if inexpensive.

**Do not block on:**
- web UI;
- customer-facing polish;
- authentication/permissions;
- perfect alias/brand taxonomy;
- every GLEIF relationship class;
- every EDGAR filing pattern;
- automatic infrastructure attribution.

Success criterion:

> The CLI saves meaningful time during a real ASM customer onboarding and
> clearly shows the operator what Helix found, why it found it, and what still
> requires manual review.

