# Corporate Helix — identity accuracy benchmark (candidate set)

This directory contains **30 candidate cases, not 30 verified answers**. The first 20 are from the prior REVIEW_REQUIRED cohort; the final 10 are proposed additional cases. Nothing here should be used as ground truth until independently verified.

## Research contract

For each case, establish the intended subject, expected relationship type, target legal entity, LEI where supported, and citations with publication/access dates. A missing LEI does not mean the company does not exist. Record evidence conflicts and distinguish no match in available sources from proof of nonexistence.

Keep `verification_status=PENDING` until an independent reviewer confirms the claim and evidence. Never use the resolver's own output as the expected answer. Do not insert benchmark-specific company exceptions into production logic.

## Scoring contract

Score only independently verified cases. A claimed SAME_LEGAL_ENTITY for a brand, subsidiary, or unrelated lookalike is a false-positive automatic resolution. Track incorrect auto-resolves, correct auto-resolves, correct review decisions, and unresolved coverage separately. An abstention is not a correct identification. Thirty cases are a safety regression suite, not proof of production-level precision.

## Immediate safety change

The `sole_uncontested` path now returns `REVIEW_REQUIRED` instead of `AUTO_RESOLVED`. Other auto-resolution paths remain unchanged and require separate audit.

## Run local regression tests

From repository root: `python3 tests/test_root_entity_resolver.py`
