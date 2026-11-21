"""Risk Topic Agreement for /risksummary.

Gold phrases (evaluation/gold_risk_topics.json) are mapped to the shared topic taxonomy. Each predicted bullet is
mapped the same way. topic-F1 = harmonic mean of
  precision : share of bullets whose topic is a gold topic
  recall    : share of gold topics covered by at least one bullet
The kit's original token-overlap proxy is reported too. Also checks the format contract (3-5 bullets, each
with a citation, <=20 words).
"""
import argparse, json, re
from _common import Api, add_common_args, load_gold
from metrics import mean, token_set_f1, topic_f1
from app.topics import detect_topics


def _tok(s):
    return set(re.findall(r"\w+", s.lower()))


def run(api: Api, max_bullets=None, only=None):
    gold = load_gold()
    per = []
    for fid, phrases in gold.items():
        if only and fid not in only:
            continue
        payload = {"filing_id": fid}
        if max_bullets:
            payload["max_bullets"] = max_bullets
        resp = api.app_post("/risksummary", payload)
        bullets = resp.get("summary", [])
        gold_topics = set().union(*[set(detect_topics(p)) for p in phrases])
        bt = [set(detect_topics(b)) for b in bullets]
        p, r, f = topic_f1(bt, gold_topics)
        per.append(dict(filing_id=fid, gold=sorted(gold_topics), pred=[sorted(t) for t in bt], summary=bullets,
                        precision=p, recall=r, f1=f,
                        token_f1=token_set_f1(_tok(" ".join(phrases)), _tok(" ".join(bullets))),
                        n=len(bullets), cited=len(resp.get("citations", [])) == len(bullets),
                        max_words=max((len(b.split()) for b in bullets), default=0)))
    out = {
        "n_filings": len(per), "topic_f1": mean(p["f1"] for p in per),
        "topic_precision": mean(p["precision"] for p in per), "topic_recall": mean(p["recall"] for p in per),
        "kit_token_f1_proxy": mean(p["token_f1"] for p in per),
        "avg_bullets": mean(p["n"] for p in per),
        "format_ok": mean(1.0 if (3 <= p["n"] <= 5 and p["cited"] and p["max_words"] <= 20) else 0.0 for p in per),
    }
    return out, per


def main():
    ap = add_common_args(argparse.ArgumentParser(description=__doc__.splitlines()[0]))
    ap.add_argument("--filing", action="append", help="limit to these filing ids")
    ap.add_argument("--max-bullets", type=int, choices=[3, 4, 5])
    ap.add_argument("--sweep", action="store_true", help="report topic-F1 for 3, 4 and 5 bullets")
    a = ap.parse_args()
    api = Api(a.inprocess)
    if a.sweep:
        for n in (3, 4, 5):
            o, _ = run(api, n, a.filing)
            print(f"bullets={n}: topic-F1={o['topic_f1']:.2f} (P={o['topic_precision']:.2f} R={o['topic_recall']:.2f})")
        return
    out, per = run(api, a.max_bullets, a.filing)
    if a.json:
        print(json.dumps(out, indent=2)); return
    print(f"Risk Topic Agreement F1: {out['topic_f1']:.2f}  (precision {out['topic_precision']:.2f}, recall {out['topic_recall']:.2f}; "
          f"{out['n_filings']} filings, avg {out['avg_bullets']:.1f} bullets)")
    print(f"Kit token-overlap proxy: {out['kit_token_f1_proxy']:.2f}   Format contract satisfied: {out['format_ok']:.0%}")


if __name__ == "__main__":
    main()
