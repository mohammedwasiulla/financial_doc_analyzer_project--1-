"""Answer quality for /qa.

  Answer-F1   : SQuAD-style token F1 between the answer and the hand-written reference (answerable questions)
  Recall      : share of reference tokens present in the answer (answers are intentionally a bit longer)
  Citation acc: answer cites the gold filing and section
  Abstention  : unanswerable questions must return "I don't know"; also reports false-IDK on answerable ones
"""
import argparse, json
from _common import Api, add_common_args, load_eval
from metrics import mean, token_f1

IDK = "i don't know"


def run(api: Api, split: str = "all", parse_only: bool = False):
    per = []
    for r in load_eval():
        if split != "all" and r["split"] != split:
            continue
        fids = r["filing_id"].split(";")
        has_id = any(f in r["question"].replace("-", "_") for f in fids)
        if parse_only and not has_id:
            continue
        payload = {"question": r["question"], "filing_id": None if (parse_only or len(fids) > 1) else fids[0]}
        resp = api.app_post("/qa", payload)
        ans = resp.get("answer", "")
        is_idk = ans.strip().lower().startswith(IDK)
        row = dict(question=r["question"], split=r["split"], expect=r["expect_answer"] == "1", answer=ans,
                   idk=is_idk, confidence=resp.get("confidence"), citations=resp.get("citations", []),
                   reference=r["reference_answer"])
        if row["expect"]:
            p, rec, f = token_f1("" if is_idk else ans, r["reference_answer"])
            secs = set(r["gold_section"].split("|"))
            cited = {(c["filing_id"], c["section"]) for c in row["citations"]}
            row.update(precision=p, recall=rec, f1=f,
                       cite_ok=bool(cited) and all(c[0] in fids and c[1] in secs for c in cited)
                       and {c[0] for c in cited} == set(fids))
        per.append(row)
    ans_rows = [p for p in per if p["expect"]]
    neg_rows = [p for p in per if not p["expect"]]
    out = {
        "n_answerable": len(ans_rows), "n_unanswerable": len(neg_rows),
        "answer_f1": mean(p["f1"] for p in ans_rows),
        "answer_recall": mean(p["recall"] for p in ans_rows),
        "answer_precision": mean(p["precision"] for p in ans_rows),
        "citation_accuracy": mean(1.0 if p["cite_ok"] else 0.0 for p in ans_rows),
        "false_idk_rate": mean(1.0 if p["idk"] else 0.0 for p in ans_rows),
        "abstention_accuracy": mean(1.0 if p["idk"] else 0.0 for p in neg_rows),
    }
    return out, per


def main():
    ap = add_common_args(argparse.ArgumentParser(description=__doc__.splitlines()[0]))
    ap.add_argument("--split", default="all", choices=["all", "dev", "test"])
    ap.add_argument("--parse-only", action="store_true",
                    help="send only the question text (filing id must be parsed from it)")
    a = ap.parse_args()
    out, _ = run(Api(a.inprocess), a.split, a.parse_only)
    if a.json:
        print(json.dumps(out, indent=2)); return
    print(f"Answer-F1: {out['answer_f1']:.2f}   (recall {out['answer_recall']:.2f}, precision {out['answer_precision']:.2f}; n={out['n_answerable']})")
    print(f"Citation accuracy: {out['citation_accuracy']:.2f}   False-IDK rate: {out['false_idk_rate']:.2f}   "
          f"Abstention accuracy: {out['abstention_accuracy']:.2f} (n={out['n_unanswerable']})")


if __name__ == "__main__":
    main()
