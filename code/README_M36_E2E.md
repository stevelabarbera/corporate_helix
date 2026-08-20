# M3.6 End-to-End REVIEW + Ollama Test

Adds:
- `create_review_fixture.py`
- `ollama_adjudicate.py`
- `run_m36_e2e.py`

Requires your existing:
- M3.5 v2 adjudication engine
- M3.6 v2.1 `evidence_packet.py`
- `build_review_queue.py`
- `show_review_queue.py`

## 1. Check installed Ollama models

```bash
ollama list
```

## 2. Deterministic path first

```bash
python3 ./code/run_m36_e2e.py
```

Expected:
- fixture written
- exactly one candidate
- deterministic decision is REVIEW
- one packet appears in `data/review/e2e_pending.jsonl`

## 3. Full path including Ollama

Choose a model shown by `ollama list`:

```bash
python3 ./code/run_m36_e2e.py --model YOUR_MODEL_NAME
```

The local adjudicator calls:
`http://localhost:11434/api/chat`

It requests schema-constrained structured output and validates:
- decision
- confidence
- evidence IDs
- rationale

Expected for this intentionally underdetermined fixture:
`AMBIGUOUS` is the safest outcome. A model returning `SAME_ENTITY` solely
because of similar names/shared address is a useful failure signal, not
something the pipeline should silently accept.

Outputs:
```text
data/review/e2e_pending.jsonl
data/review/e2e_llm_adjudicated.jsonl
```

The LLM result is attached to the pending packet for later human comparison.
It does NOT become the final graph decision automatically.
