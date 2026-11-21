"""Run the ORIGINAL starter-kit logic (baseline/kit_app) on the same eval set and compare with this project."""
import argparse, json, sys
from _common import Api, ROOT, load_eval, load_gold, add_common_args, MOCK_BASE
from metrics import mean, token_f1, topic_f1
from app.topics import detect_topics
import eval_answer_f1 as A, eval_risk_agreement as K

IDK = "i don't know"


class _Shim:
    """Route the baseline's bare requests.get/post into the in-process mock."""
    def __init__(self, tc): self.tc = tc
    def get(self, url, params=None, timeout=None): return self.tc.get(url.split("8030", 1)[1], params=params)
    def post(self, url, json=None, timeout=None): return self.tc.post(url.split("8030", 1)[1], json=json)


def run():
    api = Api(True)
    import types
    shim = _Shim(api._mock)
    sys.modules["requests"] = types.SimpleNamespace(get=shim.get, post=shim.post)   # kit modules do `import requests`
    from baseline.kit_app import analyzer as ka, retrieval as kr, tools as kt
    # QA
    per = []
    for r in load_eval():
        fids = r["filing_id"].split(";")
        resp = ka.answer_question(r["question"], fids[0] if len(fids) == 1 else None)
        idk = resp["answer"].strip().lower().startswith(IDK)
        row = dict(split=r["split"], expect=r["expect_answer"] == "1", idk=idk)
        if row["expect"]:
            row["f1"] = token_f1("" if idk else resp["answer"], r["reference_answer"])[2]
            secs = set(r["gold_section"].split("|"))
            cited = {(c["filing_id"], c["section"]) for c in resp["citations"]}
            row["cite_ok"] = bool(cited) and all(c[0] in fids and c[1] in secs for c in cited) and {c[0] for c in cited} == set(fids)
        per.append(row)
    a = [p for p in per if p["expect"]]; n = [p for p in per if not p["expect"]]
    qa = {"answer_f1": mean(p["f1"] for p in a), "citation_accuracy": mean(1.0 if p["cite_ok"] else 0.0 for p in a),
          "false_idk_rate": mean(1.0 if p["idk"] else 0.0 for p in a), "abstention_accuracy": mean(1.0 if p["idk"] else 0.0 for p in n)}
    # risk
    gold = load_gold(); fs = []
    for fid, ph in gold.items():
        bullets = ka.summarize_risks(fid)["summary"]
        g = set().union(*[set(detect_topics(p)) for p in ph])
        fs.append(topic_f1([set(detect_topics(b)) for b in bullets], g)[2])
    return {"baseline_qa": qa, "baseline_risk_topic_f1": mean(fs)}


if __name__ == "__main__":
    ap = add_common_args(argparse.ArgumentParser()); ap.parse_args()
    print(json.dumps(run(), indent=2))
