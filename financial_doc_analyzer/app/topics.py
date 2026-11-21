"""Risk-topic taxonomy shared by Q&A concept matching, risk summarisation and topic-F1 evaluation.

Keywords are matched as word-prefixes (``cyber`` matches *cybersecurity*). Keep keywords specific:
a keyword that appears in several topics makes topic-F1 ambiguous.
"""
import re
from typing import Dict, List

TOPICS: Dict[str, Dict] = {
    "cybersecurity": {"label": "Cybersecurity & data breaches",
        "kw": ["cyber", "breach", "hack", "ransomware", "malware", "fraud", "unauthorized access",
               "security incident", "account takeover"]},
    "supply_chain": {"label": "Supply chain & vendor concentration",
        "kw": ["supply", "single-source", "sole-source", "vendor", "supplier", "fulfillment", "procurement", "logistics"]},
    "privacy_regulation": {"label": "Privacy regulation",
        "kw": ["privacy", "gdpr", "ccpa", "hipaa", "data protection", "personal data", "protected health"]},
    "regulatory_compliance": {"label": "Regulatory compliance",
        "kw": ["regulator", "compliance", "financial reporting", "licens", "anti-money", "aml",
               "psd2", "reporting standard", "reimbursement policy"]},
    "customer_sla": {"label": "Customer churn & SLA performance",
        "kw": ["churn", "service-level", "service level", "sla", "customer retention", "uptime"]},
    "fx": {"label": "Foreign exchange volatility",
        "kw": ["foreign exchange", "currenc", "fx", "exchange rate"]},
    "litigation": {"label": "Litigation exposure",
        "kw": ["litigation", "lawsuit", "legal proceeding", "infring", "patent", "complaint", "class action", "court"]},
    "competition": {"label": "Competition & pricing pressure",
        "kw": ["compet", "pricing pressure", "price pressure", "interchange", "market share"]},
    "interest_rate": {"label": "Interest-rate exposure",
        "kw": ["interest rate", "funding cost", "borrowing cost", "float"]},
    "talent": {"label": "Talent retention",
        "kw": ["talent", "attrition", "key personnel", "retain", "workforce", "data scientist"]},
    "customer_concentration": {"label": "Customer concentration",
        "kw": ["customer concentration", "significant portion of", "largest customer", "top customer", "key customer"]},
}

# topics that belong to the "Risk Factors" family when used as a question cue
_COMPILED = {tid: [(kw, re.compile(r"\b" + re.escape(kw))) for kw in t["kw"]] for tid, t in TOPICS.items()}


def label(topic_id: str) -> str:
    return TOPICS.get(topic_id, {}).get("label", topic_id)


def topic_hits(text: str) -> Dict[str, int]:
    """topic id -> number of distinct keywords found in ``text``."""
    low = text.lower()
    out: Dict[str, int] = {}
    for tid, kws in _COMPILED.items():
        n = sum(1 for _, rx in kws if rx.search(low))
        if n:
            out[tid] = n
    return out


def detect_topics(text: str) -> List[str]:
    """Topics with the maximum keyword count (ties are all returned: a clause can span two topics)."""
    hits = topic_hits(text)
    if not hits:
        return []
    m = max(hits.values())
    return sorted(t for t, n in hits.items() if n == m)


def topic_spans(text: str) -> Dict[str, List[tuple]]:
    """topic id -> character spans of its keywords in ``text`` (used to consume tokens in questions)."""
    low = text.lower()
    out: Dict[str, List[tuple]] = {}
    for tid, kws in _COMPILED.items():
        for _, rx in kws:
            for m in rx.finditer(low):
                end = m.end()
                while end < len(low) and (low[end].isalnum() or low[end] == "-"):
                    end += 1
                out.setdefault(tid, []).append((m.start(), end))
    return out
