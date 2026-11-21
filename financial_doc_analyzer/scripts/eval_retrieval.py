"""Retrieval quality: Precision@5 (+ Hit@5, MRR) at (filing, section) level.

A result is relevant if its filing is one of the question's target filings AND its section is one of the
gold sections in evaluation/eval_qna.csv. Two systems are compared:
  baseline : the gateway's raw /search with the raw question (what the starter kit's script measured)
  app      : this project's retrieval layer (query cleaning + concept expansion + clause-level rerank)
"""
import argparse, json, re
from _common import Api, add_common_args, load_eval
from metrics import hit_at_k, mean, precision_at_k, reciprocal_rank

KIT_PROXY_NOTE = "kit proxy = any answer term appears in the top-5 snippets (raw /search)"


def run(api: Api, split: str = "all"):
    rows = [r for r in load_eval() if r["expect_answer"] == "1" and (split == "all" or r["split"] == split)]
    per = []
    for r in rows:
        fids = r["filing_id"].split(";")
        secs = set(r["gold_section"].split("|"))
        rel = {(f, s) for f in fids for s in secs}
        # baseline: raw question to raw /search, once per target filing, merged by score
        merged = []
        for f in fids:
            merged += api.mock_get("/search", q=r["question"], filing_id=f, top_k=5).get("results", [])
        merged.sort(key=lambda h: -h["score"])
        base = [(h["filing_id"], h["section"]) for h in merged][:5]
        snippets = " ".join(h.get("snippet", "").lower() for h in merged[:5])
        proxy = any(t.lower() in snippets for t in r["answer_terms"].split(";") if t)
        # app retrieval (question only when several filings, else scoped by filing_id)
        payload = {"question": r["question"], "filing_id": fids[0] if len(fids) == 1 else None}
        app = [(h["filing_id"], h["section"]) for h in api.app_post("/debug/retrieve", payload, top_k=5)]
        per.append(dict(question=r["question"], split=r["split"], gold=sorted(rel), baseline=base, app=app,
                        p_base=precision_at_k(base, rel), p_app=precision_at_k(app, rel),
                        hit_base=hit_at_k(base, rel), hit_app=hit_at_k(app, rel),
                        rr_base=reciprocal_rank(base, rel), rr_app=reciprocal_rank(app, rel), proxy=proxy,
                        n_base=len(base), n_app=len(app)))
    out = {
        "n": len(per),
        "baseline": {"precision@5": mean(p["p_base"] for p in per), "hit@5": mean(p["hit_base"] for p in per),
                     "mrr": mean(p["rr_base"] for p in per), "avg_results": mean(p["n_base"] for p in per),
                     "kit_proxy_precision@5": mean(1.0 if p["proxy"] else 0.0 for p in per)},
        "app": {"precision@5": mean(p["p_app"] for p in per), "hit@5": mean(p["hit_app"] for p in per),
                "mrr": mean(p["rr_app"] for p in per), "avg_results": mean(p["n_app"] for p in per)},
    }
    return out, per


def main():
    ap = add_common_args(argparse.ArgumentParser(description=__doc__.splitlines()[0]))
    ap.add_argument("--split", default="all", choices=["all", "dev", "test"])
    a = ap.parse_args()
    out, per = run(Api(a.inprocess), a.split)
    if a.json:
        print(json.dumps(out, indent=2)); return
    print(f"Retrieval on {out['n']} answerable questions (split={a.split})")
    for name in ("baseline", "app"):
        m = out[name]
        print(f"  {name:8s} Precision@5={m['precision@5']:.2f}  Hit@5={m['hit@5']:.2f}  MRR={m['mrr']:.2f}  avg results returned={m['avg_results']:.1f}")
    print(f"  ({KIT_PROXY_NOTE}): {out['baseline']['kit_proxy_precision@5']:.2f}")


if __name__ == "__main__":
    main()
