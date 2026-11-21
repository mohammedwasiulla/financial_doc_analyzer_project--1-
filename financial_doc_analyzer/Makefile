.PHONY: install corpus mock app test eval eval-live demo
install:   ; pip install -r requirements.txt
corpus:    ; python scripts/generate_corpus.py          # fills the corpus up to 15 filings (never overwrites)
mock:      ; cd mock_server && uvicorn main:app --port 8030 --reload
app:       ; MOCK_BASE_URL=http://127.0.0.1:8030 uvicorn app.server:app --port 9025 --reload
test:      ; python -m pytest -q tests
eval:      ; python scripts/run_all_evals.py --inprocess    # no servers needed
eval-live: ; python scripts/run_all_evals.py               # needs `make mock` and `make app` running
demo:      ; python scripts/demo.py
