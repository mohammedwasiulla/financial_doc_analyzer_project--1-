# Automated Compliance Insights & Risk Summarization Engine

A retrieval-based, clause-aware analysis agent for 10-K-style filings. Two FastAPI endpoints sit on top of a
retrieval gateway (a mock over synthetic filings today, a real EDGAR gateway later - see `RUNBOOK.md`):

| Endpoint | Input | Output |
|---|---|---|
| `POST /qa` | `question` (+ optional `filing_id`) | 2-3 sentence answer, citations `[{filing_id, section}]`, confidence, evidence quotes. Returns **"I don't know."** when confidence is low |
| `POST /risksummary` | `filing_id` (+ optional `max_bullets` 3-5) | 3-5 bullets (<=20 words), one citation per bullet |

Everything is extractive and deterministic: no LLM or API key is needed, every sentence in an answer is a clause
from the filing, so every answer is checkable against its citation.

## Quick start
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python scripts/generate_corpus.py        # only needed if corpus/filings has fewer than 15 files (already included)

# terminal 1 - mock retrieval gateway (port 8030)
cd mock_server && uvicorn main:app --port 8030
# terminal 2 - the app (port 9025)
MOCK_BASE_URL=http://127.0.0.1:8030 uvicorn app.server:app --port 9025
```
Interactive docs: http://127.0.0.1:9025/docs. Or `docker compose up --build`. `make` targets: `install corpus mock app test eval eval-live demo`.

```bash
curl -s 127.0.0.1:9025/qa -H 'content-type: application/json' \
  -d '{"question":"What are the cybersecurity risks for ACMR-2023?"}'
curl -s 127.0.0.1:9025/risksummary -H 'content-type: application/json' -d '{"filing_id":"HLXR_2022"}'
```

## What is in the box
```
app/            client.py (gateway HTTP + retries)  retrieval.py (/search layer)  tools.py (/tools/risk/score)
                analyzer.py (Q&A + risk summary)  topics.py (risk taxonomy)  text_utils.py  models.py  server.py
mock_server/    mock retrieval gateway (kit's, with additive changes - see below)
corpus/filings/ 15 synthetic filings: ACMR FINC ZYNT QRTX HLXR x FY2021-2023
scripts/        eval_retrieval.py  eval_answer_f1.py  eval_risk_agreement.py  run_all_evals.py
                compare_baseline.py  generate_corpus.py  demo.py  metrics.py
evaluation/     eval_qna.csv (53 questions)  gold_risk_topics.json (15 filings)  results/{metrics.json,cases.md}
tests/          28 pytest tests (units, API contract, failure modes, HTTP client)
baseline/       the starter kit's original logic, kept only so it can be measured on the same data
docs            README.md  RUNBOOK.md  IMPLEMENTATION_NOTES.md  EVALUATION_SUMMARY.md
```

## Evaluate
```bash
python scripts/run_all_evals.py --inprocess     # no servers needed; writes evaluation/results/
python scripts/run_all_evals.py                 # same, against the running servers (identical results)
python scripts/eval_retrieval.py --inprocess    # Precision@5 (+Hit@5, MRR)
python scripts/eval_answer_f1.py --inprocess    # Answer-F1, citation accuracy, abstention
python scripts/eval_risk_agreement.py --inprocess [--sweep]   # topic-F1
python -m pytest -q tests
```
Headline results are in `EVALUATION_SUMMARY.md`.
