# M&A recall diagnostic — four pinned companies (initial sentinel baseline)

**Purpose:** test actual acquisition discovery rather than legal-name resolution. This is an initial, intentionally small gold set: **one verified historical transaction per company**, selected from independent corporate announcements; it is **not a representative or exhaustive M&A recall denominator**. For Monsanto, the Bayer closing is a known historical repo regression case, not a blind holdout.

The four pinned historic SEC CIKs are in `data/eval_study/ma_recall_four_v1.json`:
- Johnson & Johnson — `0000200406`, source SEC filer page
- Walmart Inc. — `0000104169`, source SEC filer page
- General Electric Company — `0000040545`, source SEC filer page (historical corporate lineage; today known as GE Aerospace)
- Monsanto Company — `0001110783`, historical SEC filer, no current ticker-directory match necessary

The independently established sentinel deals are:
- J&J completed acquisition of Abiomed, Dec 22 2022 (J&J press release)
- Walmart completed acquisition of VIZIO Holding Corp., Dec 3 2024 (Walmart press release)
- GE completed acquisition of Alstom's **Power and Grid businesses**, Nov 2 2015 (GE press release). This is an asset/business acquisition and must not silently be equated to buying all of Alstom SA.
- Bayer completed acquisition of **Monsanto Company**, June 7 2018 (Bayer press release); verify acquisition direction, not an acquisition *by* Monsanto.

Source URLs and caveats are preserved in each `data/eval_gold/ma_recall_four/*.json` file. The baseline uses existing `code/eval/run_ma_s1_baseline.py` with its already implemented stages, retained document passages and separate candidate emission. We deliberately **do not modify the source retriever, parser, or confidence/pivot thresholds**.

## Run on Mac with SEC access

First fetch the branch and run summary unit tests:

```bash
git fetch origin
git switch eval/ma-recall-four-baseline
python3 -m unittest discover -s tests -p 'test_ma_recall_four_summary.py' -v
```

Use a genuine SEC-compliant name and email in `SEC_USER_AGENT`; do not use the historical hardcoded `contact@example.com`.

```bash
export SEC_USER_AGENT='Your Real Name your-real-email@yourdomain.com'
mkdir -p data/eval_study/ma_recall_four_results
```

**Start with one company** to verify your SEC connection, extraction dependencies (e.g. spaCy), speed and output:

```bash
python3 code/eval/run_ma_s1_baseline.py \
  --study data/eval_study/ma_recall_four_v1.json \
  --gold-dir data/eval_gold/ma_recall_four \
  --results data/eval_study/ma_recall_four_results \
  --company johnson_and_johnson \
  --start 2015-01-01 --end 2026-11-24 \
  --user-agent "$SEC_USER_AGENT"
```

**Only after confirming source connectivity and runtime are acceptable**, run the other three:

```bash
for company in walmart general_electric monsanto; do
  python3 code/eval/run_ma_s1_baseline.py \
    --study data/eval_study/ma_recall_four_v1.json \
    --gold-dir data/eval_gold/ma_recall_four \
    --results data/eval_study/ma_recall_four_results \
    --company "$company" \
    --start 2015-01-01 --end 2026-11-24 \
    --user-agent "$SEC_USER_AGENT" || break
done
```

**Warning:** Existing baseline retrieval downloads documents across a large period, without a per-company file cap, and may be slow, expensive in requests, or blocked by SEC throttling. This is intentionally unchanged to avoid hiding retrieval failures. The S1 collector preserves fetch errors; inspect them, and don't score a clean recall rate when relevant evidence was not successfully retrieved. The existing baseline runner **overwrites the result JSON for the same company**; don't rerun against the same results folder unless intentionally replacing the capture.

Aggregate the four case outputs into a separate new file:

```bash
python3 code/eval/summarize_ma_recall_four.py \
  --study data/eval_study/ma_recall_four_v1.json \
  --results data/eval_study/ma_recall_four_results \
  --out data/eval_study/ma_recall_four_summary_v1.json
```

This summary reports each known deal's deepest stage and first unpassed stage, not just the number of found companies. Results absent/not-run remain `NOT_RUN` and are not treated as misses. Retrieval errors suppress the clean detection fraction.

**Evaluation cautions:**
- A discovered name alone does not equal a correctly extracted M&A event; the existing S1 scorer requires an event with matching expected type/status, while `candidate_emitted` may only measure a name candidate. Interpret stage fields separately.
- A transaction disclosed in a filer’s 10-Q, 8-K attachment, press release or target’s report may be missed because the current SEC retriever does not include that form or document. Classify this as source/retrieval coverage before claiming extraction failure.
- `SENTINEL_ONLY_NOT_ALL_MA_RECALL` is a deliberate guardrail. Four known deals cannot establish overall recall across the companies' acquisition histories. This is the start of a larger independently sourced event inventory.
- The baseline dataset is 2015-01-01 through 2026-11-24; events before or after that window are not evaluated.
- Existing Mongo/CSV, alternative commercial providers, and tenant internal data are outside this pass.

## Later, only after this baseline

1. Trace missed sentinel transactions with existing `code/eval/explain_miss.py` using pinned CIK and stored evidence.
2. Expand to a broader source-independent M&A gold set per company, with exact dates, forms, buyer/target, announcement vs closing, and source citations, before interpreting the rate as discovery recall.
3. Then return to the *older October cohort* the user mentioned and compare its objective and data sources with the newer identity-anchor impact study. Do **not** merge that prior cohort's conclusions into this M&A baseline.
