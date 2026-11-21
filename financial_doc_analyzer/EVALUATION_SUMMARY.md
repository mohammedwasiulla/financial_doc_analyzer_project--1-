# Evaluation summary (1 page)

**Setup.** 53 hand-written questions (45 answerable, 8 designed to be unanswerable) over 15 synthetic filings; 15 gold risk-topic sets.
Splits: dev 20, test 17, blind 16. All numbers reproduce with `python scripts/run_all_evals.py --inprocess` (live HTTP gives identical results).

| Metric | Starter-kit logic | This project |
|---|---|---|
| **Precision@5** (section level, 45 answerable) | 0.40 (raw `/search`) | **0.73** |
| Hit@5 / MRR | 0.89 / 0.68 | **0.98 / 0.94** |
| **Answer-F1** (token overlap vs. reference) | 0.27 | **0.65** (recall 0.79, precision 0.62) |
| Citation accuracy (right filing and section) | 0.56 | **1.00** |
| Abstention on unanswerable ("I don't know") | 0.50 | **1.00** (n=8) |
| False "I don't know" on answerable | 0.04 | 0.00 |
| **Risk Topic Agreement (topic-F1)**, 4 bullets | 0.47 | **0.70** (P 0.62, R 0.82) |

Per split Answer-F1: dev 0.61, test 0.69, blind 0.67. Topic-F1 by bullet count: 3 -> 0.67, 4 -> 0.70, 5 -> 0.73 (recall 0.98, precision 0.59).
Format contract (3-5 bullets, each cited, <=20 words): 15/15.

**Metric notes.** Precision@5 is computed over the results actually returned (the app returns ~1.8 sections, the raw API ~3.1), so returning fewer
sections helps it; Hit@5 and MRR do not have that bias. topic-F1 = bullet precision x gold-topic recall, using a shared keyword taxonomy.
The kit's token-overlap proxy scores the same summaries at 0.14, which shows why it was replaced.

## Reflections
1. **Giving retrieval the full section mattered most.** The starter API exposes 220 characters, so later bullets (FX, churn) were invisible; adding `text` fixed that.
2. **Query cleaning and clause-level re-ranking** lift Precision@5 from 0.40 to 0.73 because raw questions match on stop-words.
3. **Abstention works** because confidence is the share of question concepts a clause actually covers; partial matches say what is missing.
4. **Weak spot: risk topic-F1.** With five near-identical bullets per filing, picking 4 misses about 18% of gold topics (recall 0.82), and gold labels for the three
   kit-only filings are arbitrary subsets (FINC_2022's gold "litigation exposure" is not in its Risk Factors at all: topic-F1 0.29).

## Logged examples (full list: `evaluation/results/cases.md`)
**Good**
* "What is the revenue growth driver for HLXR_2022?" -> "Revenue grew due to new hospital system contracts and expanded payer analytics modules." (F1 1.00)
* "What does FINC_2022 say about its key markets?" -> "Key markets include APAC and North America." (0.93)
* "How did ZYNT's gross margin change from 2022 to 2023?" -> one sentence per filing (74% -> 55%), both cited.
* "What is the CEO's compensation at ACMR_2023?" -> "I don't know."

**Weak**
* "What does management say about trends in QRTX_2023?" (F1 0.20): returns the generic first MD&A sentence, not the specific "Notable trends" one; both match equally.
* "Does ACMR_2022 mention foreign exchange risk?" (0.38): correct clause, but the appended "other risks" sentence dilutes a yes/no answer.
* "Does ZYNT_2023 have any litigation?" (0.45): returns "We are subject to routine litigation." and drops the "no material effect" qualifier.
* FINC_2022 risk summary (topic-F1 0.29): see reflection 4.

## Caveats - read before quoting these numbers
* Reference answers and 12 of 15 gold topic sets were written by me; they are small, synthetic and templated. High scores say "the pipeline works on this data", not "works on 10-Ks".
* **dev/test are not held out**: I fixed generic bugs after seeing their failures. The blind set was run once *before* further fixes
  (Answer-F1 0.48, false-IDK 0.21, citation accuracy 0.79); the 0.67 above is after fixes, so it is also no longer blind.
* The first full run (37 questions) gave Answer-F1 0.46, false-IDK 0.13, citation accuracy 0.84.
* Severity cues ("infring", "defend", "inquiry") were added after seeing that the HLXR_2022 patent risk was ranked out.
