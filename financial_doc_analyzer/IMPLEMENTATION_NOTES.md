# Implementation notes

## Architecture
```
client --> FastAPI app (/qa, /risksummary) --> gateway client --> retrieval gateway (mock | real)
                |                                  /search  /doc  /doc/../section  /filings  /tools/risk/score
                +-- analyzer.py   query planning, clause scoring, confidence gate, risk ranking
                +-- topics.py     11-topic risk taxonomy shared by Q&A, summaries and evaluation
```
Deliberately no LLM: answers are verbatim clauses, so hallucination is impossible by construction, runs are
reproducible, and evaluation does not need credentials. `prompts/` holds the optional LLM wording step.

## /qa pipeline
1. **Plan the query.** Resolve scope: explicit ids (`ACMR-2023`, `ACMR_2023`, `ACMR 2023`), or ticker x year ("ZYNT ... from 2022 to 2023"),
   validated against the gateway's filing list. Extract *concepts*: topic concepts (via the taxonomy; weight 1.5) and token concepts (weight 1.0);
   drop stop/generic words; treat section words ("business", "MD&A", "legal proceedings", "risk") as intent, not content;
   a short alias table bridges "growth/grew", "driver/due to".
2. **Retrieve.** `/search` with the cleaned query expanded with topic synonyms (the mock sums raw substring counts, so stop-words in a raw question add noise).
3. **Clause scoring.** Split sections into bullets/sentences; a clause matches a concept by taxonomy hit or stem match.
   A greedy cover picks up to 3 clauses; ties prefer the section the question points at, stronger topic evidence, and the shorter (more specific) clause.
4. **Confidence = covered concept weight / total concept weight.** Below 0.55 the answer is "I don't know."
   If the first pass is low, the whole filing is scanned once (recall fallback) before giving up.
   If the answer covers only part of the question, a sentence says what the filing does not address (e.g. *hurricanes*).
5. **Compose.** Financial lines are rendered as "ACMR_2023's total revenue is $1200M."; risk answers add a one-line list of the other risks in the section;
   multi-filing questions give one sentence per filing (max 3). Answers are capped at 3 sentences; some are 1 sentence when only one fact is supported.

## /risksummary pipeline
Candidates = clauses of Risk Factors (weight 1.0), Legal Proceedings (0.6), MD&A (0.3). Score =
`min(1, api_score/0.3) + 0.5*[taxonomy hit] + 0.15*severity cues` - boilerplate penalty, where `api_score` comes from the gateway's
`/tools/risk/score`. Select top-N (default 4) with **topic diversity**; guarantee at least 3 bullets from Risk Factors; trim to 20 words;
cite each bullet's (filing, section). The taxonomy and severity cues exist because the mock helper only knows ten keywords: it scores
"patent infringement" and "attrition" as 0.

## Design decisions
* Retrieval is `/search`-first as the brief requires, with the full-document scan only as a fallback.
* `text` in `/search` results is an additive contract change; the app degrades to `/doc/../section`, then to snippets (tested).
* Abstention is a first-class output: 8 unanswerable questions (missing filing, absent topic, off-topic) are part of the eval.
* Defaults (4 bullets, 0.55 threshold) were chosen before the sweeps; sweeps are reported, not used to cherry-pick.

## Bugs found and fixed along the way (worth knowing)
Years in "from 2022 to 2023" were eaten by an over-eager id regex; two taxonomy keywords double-counted the same word and distorted topic
assignment; "breaches" stemmed to "breache"; degree/size words ("large", "intensity") counted as content. The kit's own scripts
scored Answer-F1 against keyword lists and never passed a filing id; they were replaced.

## Known limitations
* Templated synthetic text flatters keyword methods; real filings need passage retrieval, heading-aware splitting and a re-tuned taxonomy.
* No semantic matching beyond the taxonomy and ~7 aliases ("revenue per employee" -> IDK; "currency risk" works only via the taxonomy).
* Answers are verbatim clauses, so they can sound terse and cannot combine facts across clauses.
* Risk ranking is heuristic; with near-identical risk lists, which 4 of 5 bullets appear is decided by keyword density.
* Single-process, in-memory caches; no auth on the app itself.
* The gateway client uses `http.client` for plain `http://` (no proxy support) and `urllib` for `https://`; behind a corporate proxy, point it at the gateway directly or extend `UrllibSession`.

## Next steps
Passage-level retrieval + embeddings behind the same gateway contract; optional LLM rewriting constrained to the evidence (`prompts/`);
calibrated confidence from labelled data; a held-out human-labelled set on real filings.
