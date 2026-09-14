# M&A Saturation Pilot — Frozen Baseline

## Question
As Helix sees increasingly diverse issuers, do the marginal numbers of **new M&A disclosure primitives** and **new parser failure classes** trend toward zero?

A sustained flattening is empirical evidence that the practical problem space is becoming bounded; it is not proof that every possible SEC disclosure has been seen.

## Experimental rule
Freeze current Helix behavior before collecting the cohort. Do not tune retrieval, locator rules, entity fusion, event grammar, trust, or recursion between companies. Record misses first; generalized improvements happen after the baseline.

For each company record: `CIK -> filings -> relevant text -> locator -> entity -> event -> candidate`, then annotate `observed_primitives` and `failure_classes`. Labels must be reusable mechanisms, never company-specific labels.

The cohort order in `data/eval_study/ma_saturation_pilot_v1.json` is frozen because discovery order is part of the measurement. Company n contributes its first-seen primitives/failure classes to the marginal-novelty curve.

Run `python3 code/eval/run_ma_saturation.py` or add `--json`.

The first 12 companies are a probe, not a stopping rule. High novelty means expand. Apparent flattening means add diverse issuers specifically to challenge the plateau.

## Relationship to M3.9
This does not replace broad M3.9. M3.9 asks what useful corporate/legal information exists and where. This pilot asks whether today's EDGAR M&A pipeline retrieves/extracts the M&A subset and whether new disclosure/failure mechanisms saturate.
