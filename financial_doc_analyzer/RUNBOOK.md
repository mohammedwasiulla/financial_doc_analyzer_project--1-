# RUNBOOK - synthetic data today, real filings later

## 1. Operate the synthetic setup
| Task | Command |
|---|---|
| start mock + app | `make mock` / `make app` (or `docker compose up --build`) |
| health | `curl 127.0.0.1:9025/health` -> `{"status":"ok","gateway":"reachable","filings":15}` |
| regenerate missing corpus files | `python scripts/generate_corpus.py` (`--force` overwrites) |
| add your own synthetic filing | drop `TICKER_YYYY.md` into `corpus/filings/` with `## Business`, `## Risk Factors` (one `- ` bullet per risk), `## MD&A`, `## Legal Proceedings`, `## Financials`. The mock picks it up on the next request (no restart) |
| run tests / evals | `make test`, `make eval` |
| gateway down? | app returns 503; `curl 127.0.0.1:8030/health`; check `MOCK_BASE_URL` |

## 2. The gateway contract the app depends on
The app only talks to a gateway through `app/client.py`. Anything that implements this contract works:

| Endpoint | Required | Notes |
|---|---|---|
| `GET /search?q&filing_id&top_k` -> `{results:[{filing_id, section, score, snippet, text?}]}` | yes | `text` = full text of the section/passage. If absent the app calls the section endpoint, then falls back to `snippet` (answers may be truncated) |
| `GET /doc/{filing_id}` -> `{exists, sections:[...]}` | yes | used for existence checks and the full-document recall fallback |
| `GET /doc/{filing_id}/section/{section}` -> `{text}` | recommended | 404 is tolerated |
| `GET /filings` -> `{filings:[ids]}` | recommended | 404 tolerated; the app then discovers ids via a broad `/search` |
| `POST /tools/risk/score` `{text}` -> `{score}` | yes (for `/risksummary`) | higher = riskier clause |

Filing ids are `TICKER_YYYY`; section names are `Business`, `Risk Factors`, `MD&A`, `Legal Proceedings`, `Financials`.

## 3. Switching to a real EDGAR gateway
**The URL switch is the easy 10%.** Set
```bash
export MOCK_BASE_URL=https://<your-edgar-gateway>     # no trailing slash
export GATEWAY_API_KEY=<token>                        # sent as "Authorization: Bearer ..."
```
and restart the app. The harder part is that *EDGAR itself does not expose this API*; you need a gateway service
that does. Design notes (not implemented or tested here - the build sandbox could not reach sec.gov):

1. **Filing index.** Map `TICKER_YYYY` to an accession number: ticker -> CIK -> `https://data.sec.gov/submissions/CIK##########.json`,
   pick the 10-K whose fiscal year matches. Cache the mapping; serve it from `GET /filings`.
2. **Fetch and parse.** Download the primary 10-K document from `https://www.sec.gov/Archives/edgar/data/...`.
   SEC fair-access rules: send a descriptive `User-Agent` with contact details and stay under 10 requests/second.
   Convert HTML to text and split on the Item headings: Item 1 -> `Business`, Item 1A -> `Risk Factors`,
   Item 3 -> `Legal Proceedings`, Item 7 -> `MD&A`, Item 8 / XBRL "company facts" -> `Financials`.
3. **Return passages, not whole items.** A real Item 1A is tens of pages. `/search` should return ranked passages
   (a few hundred words, labelled with their section) in `text`; the app treats each hit's text as clause source, so this works unchanged.
   Real risk factors are paragraphs with headings, not one-line bullets: `split_clauses` handles sentences,
   but a heading-aware splitter is a worthwhile upgrade.
4. **Risk score endpoint.** Reuse the keyword helper or replace it with a model; the app only needs a float.
5. **Re-tune before trusting numbers.** The topic taxonomy (`app/topics.py`), alias list and `QA_MIN_CONFIDENCE`
   were developed against templated synthetic text. Build a new labelled set from a handful of real filings and re-run
   `scripts/run_all_evals.py` (the scripts read `evaluation/*.csv|json`, so only the data changes).
6. **Rollout checklist:** point a staging app at the gateway -> `/health` shows filings > 0 -> spot-check 20 questions against the
   cited passages -> compare abstention behaviour (it must still say "I don't know" for off-topic questions) -> then switch production.

## 4. Rolling back
Unset `MOCK_BASE_URL` / `GATEWAY_API_KEY` (or set them back to the mock) and restart. No data migrations exist.
