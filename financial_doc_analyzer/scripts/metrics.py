"""Metric definitions (pure functions, unit-tested)."""
import re, string
from collections import Counter
from typing import Dict, Iterable, List, Sequence, Set, Tuple

_ART = re.compile(r"\b(a|an|the)\b")


def norm_tokens(s: str) -> List[str]:
    """SQuAD-style normalisation: lower-case, strip punctuation and articles."""
    s = s.lower().replace("_", " ")
    s = re.sub(r"'s\b", "", s)            # possessives: "ACMR_2023's" -> "acmr 2023"
    s = "".join(ch for ch in s if ch not in set(string.punctuation))
    s = _ART.sub(" ", s)
    return s.split()


def token_f1(pred: str, gold: str) -> Tuple[float, float, float]:
    """(precision, recall, F1) over the multiset of normalised tokens."""
    p, g = Counter(norm_tokens(pred)), Counter(norm_tokens(gold))
    common = sum((p & g).values())
    if not p or not g or common == 0:
        return 0.0, 0.0, 0.0
    prec, rec = common / sum(p.values()), common / sum(g.values())
    return prec, rec, 2 * prec * rec / (prec + rec)


def precision_at_k(ranked: Sequence[Tuple[str, str]], relevant: Set[Tuple[str, str]], k: int = 5) -> float:
    """Relevant fraction of the (<=k) results actually returned."""
    top = list(ranked)[:k]
    return sum(1 for r in top if r in relevant) / len(top) if top else 0.0


def hit_at_k(ranked, relevant, k: int = 5) -> float:
    return 1.0 if any(r in relevant for r in list(ranked)[:k]) else 0.0


def reciprocal_rank(ranked, relevant) -> float:
    for i, r in enumerate(ranked, 1):
        if r in relevant:
            return 1.0 / i
    return 0.0


def topic_f1(bullet_topics: List[Set[str]], gold: Set[str]) -> Tuple[float, float, float]:
    """Bullet-level precision (a bullet is correct if any of its topics is gold) x gold-topic recall."""
    if not bullet_topics or not gold:
        return 0.0, 0.0, 0.0
    prec = sum(1 for t in bullet_topics if t & gold) / len(bullet_topics)
    pred = set().union(*bullet_topics)
    rec = len(pred & gold) / len(gold)
    f = 0.0 if prec + rec == 0 else 2 * prec * rec / (prec + rec)
    return prec, rec, f


def token_set_f1(gold_terms: Set[str], model_terms: Set[str]) -> float:
    """The kit's original proxy (token-set overlap), kept for continuity."""
    if not gold_terms or not model_terms:
        return 0.0
    inter = len(gold_terms & model_terms)
    p, r = inter / len(model_terms), inter / len(gold_terms)
    return 0.0 if p + r == 0 else 2 * p * r / (p + r)


def mean(xs: Iterable[float]) -> float:
    xs = list(xs)
    return sum(xs) / len(xs) if xs else 0.0
