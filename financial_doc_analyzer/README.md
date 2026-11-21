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

## Things you should know about the starter kit
* **The kit shipped 6 filings (3 companies, FY2022-23), not the 15 x 5 in the brief.** `scripts/generate_corpus.py`
  adds the 9 missing ones (ACMR/FINC/ZYNT FY2021 and two new synthetic companies, QRTX and HLXR). The original 6 are untouched.
* **Mock server changes (additive; old clients keep working):** `/search` results gain a `text` field (full section),
  plus `GET /doc/{id}/section/{name}`, `GET /filings`, `GET /health`, a `CORPUS_DIR` env var, and filing-id validation
  (the original joined the raw id into a file path). Without `text`, the kit's `/search` only exposes the first 220
  characters of a section, so a risk summary could never see beyond the first bullet or two.
* The kit's `docker-compose.yml` referenced Dockerfiles that did not exist; they are added.
* ZYNT_2023's MD&A says "higher cloud gross margins" while its Financials show gross margin falling from 74% to 55%.
  This is an inconsistency in the synthetic data; the app reports what each section says.

## Configuration (env vars)
`MOCK_BASE_URL` (default `http://127.0.0.1:8030`), `GATEWAY_API_KEY` (sent as Bearer token), `HTTP_TIMEOUT` (10 s),
`QA_MIN_CONFIDENCE` (0.55), `RISK_BULLETS` (4; allowed 3-5).

## Errors
Unknown filing in `/risksummary` -> 404. Malformed input -> 422. Gateway down -> 503 with a clear message
(`/health` reports `degraded`). `/qa` about an unknown filing -> "I don't know." with a note.

## Troubleshooting
* **A command freezes, and Ctrl+C shows a traceback ending in `create_urllib3_context` / `SSLContext`** (seen on Windows with
  Microsoft Store Python): the `requests` package builds an SSL context when imported, which can stall. This project no longer
  uses `requests` or `httpx`: the app and scripts call the gateway with the standard library (`app/client.py`) and the tests use an
  in-memory ASGI client (`app/asgi_client.py`), so nothing here creates an SSL context for plain `http://` URLs.
  If you still see it, it is coming from another package in your environment: run in a fresh `.venv`.
* **`TimeoutError: timed out` from `demo.py` or an eval script:** the app did not answer in time. Check that BOTH servers are running
  (mock on 8030, app on 9025) and look at the app terminal for errors. The project connects to `127.0.0.1` rather than `localhost`
  on purpose: on Windows, `localhost` tries IPv6 first, which adds about 2 seconds to every new connection.
* **Connection refused:** the mock server (port 8030) is not running. **Port in use:** stop the old server or change `--port`.
* **Windows PowerShell:** set `$env:MOCK_BASE_URL="http://127.0.0.1:8030"` before starting the app if you changed the mock's port.

## Demo video
`demo/demo_video.mp4` (about 3m15s): setup, both server starts, the endpoints, tests and every evaluation script running against the live servers.
It was rendered from real captured output, not recorded from a screen. To record your own,
start both servers and run `python scripts/demo.py` while your screen recorder is on.
