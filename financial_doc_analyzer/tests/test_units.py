import json, os
from app.text_utils import find_filing_ids, find_years, split_clauses, stem, normalize_filing_id, remove_ids
from app.topics import detect_topics
from metrics import token_f1, precision_at_k, topic_f1, reciprocal_rank
from generate_corpus import FILINGS


def test_filing_id_parsing():
    assert find_filing_ids("cybersecurity risks for ACMR-2023?") == ["ACMR_2023"]
    assert find_filing_ids("acmr_2022 vs ZYNT 2023") == ["ACMR_2022", "ZYNT_2023"]
    assert find_filing_ids("in FY 2023 and from 2022 to 2023") == []
    assert normalize_filing_id("qrtx-2021") == "QRTX_2021"
    assert find_years(remove_ids("from 2022 to 2023 for ACMR_2021")) == ["2022", "2023"]


def test_clause_split():
    assert split_clauses("- a one.\n- b two.") == ["a one.", "b two."]
    assert split_clauses("Total revenue: $1200M. Gross margin: 77%.") == ["Total revenue: $1200M.", "Gross margin: 77%."]
    assert stem("breaches") == "breach" and stem("penalties") == "penalty"


def test_topic_detector_recovers_intended_topics():
    bad = []
    for fid, d in FILINGS.items():
        for intended, bullet in d["risks"]:
            if intended not in detect_topics(bullet):
                bad.append((fid, intended, bullet))
    assert not bad, bad


def test_gold_phrases_map_to_a_topic():
    gold = json.load(open(os.path.join(os.path.dirname(__file__), "..", "evaluation", "gold_risk_topics.json")))
    for fid, phrases in gold.items():
        for p in phrases:
            assert detect_topics(p), (fid, p)


def test_metrics():
    assert token_f1("The ACMR_2023's revenue is $1200M", "ACMR revenue 2023 $1200M")[2] > 0.7
    assert token_f1("", "x") == (0.0, 0.0, 0.0)
    rel = {("A", "Risk Factors")}
    assert precision_at_k([("A", "Risk Factors"), ("A", "Business")], rel) == 0.5
    assert reciprocal_rank([("B", "x"), ("A", "Risk Factors")], rel) == 0.5
    assert topic_f1([{"a"}, {"b"}], {"a", "c"}) == (0.5, 0.5, 0.5)
