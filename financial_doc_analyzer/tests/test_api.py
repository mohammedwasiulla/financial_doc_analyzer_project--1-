import pytest


def qa(api, q, fid=None):
    r = api.post("/qa", json={"question": q, "filing_id": fid})
    assert r.status_code == 200, r.text
    return r.json()


def test_qa_cybersecurity_with_citation(api):
    r = qa(api, "What are the cybersecurity risks for ACMR-2023?")
    assert "data breaches" in r["answer"]
    assert {"filing_id": "ACMR_2023", "section": "Risk Factors"} in r["citations"]
    assert 1 <= r["answer"].count(". ") + 1 <= 3          # 2-3 sentences max


def test_qa_financial_fact_and_scoping(api):
    assert "55%" in qa(api, "What was the gross margin for ZYNT 2023?")["answer"]
    assert "$402M" in qa(api, "revenue", "QRTX_2022")["answer"]


@pytest.mark.parametrize("q", ["What is the CEO's compensation at ACMR_2023?",
                               "Does ACMR_2023 have climate change risk?",
                               "What talent risks does QRTX_2023 face?",
                               "What cybersecurity risks does ACMR_2020 have?",
                               "What is the weather in Paris?"])
def test_qa_idk(api, q):
    r = qa(api, q)
    assert r["answer"] == "I don't know." and r["citations"] == []


def test_qa_compare_two_filings(api):
    r = qa(api, "How did ZYNT's gross margin change from 2022 to 2023?")
    assert "74%" in r["answer"] and "55%" in r["answer"]
    assert {c["filing_id"] for c in r["citations"]} == {"ZYNT_2022", "ZYNT_2023"}


def test_qa_unscoped_section_question_asks_for_filing(api):
    r = qa(api, "What are the key risks?")
    assert r["answer"] == "I don't know." and "filing" in r["note"].lower()


def test_qa_partial_match_is_flagged(api):
    r = qa(api, "Does ACMR_2023 face supply chain risk from hurricanes?")
    assert "single-source" in r["answer"] and "hurricane" in r["answer"]


def test_risksummary_contract(api):
    for fid in ["ACMR_2023", "QRTX_2023", "HLXR_2022"]:
        r = api.post("/risksummary", json={"filing_id": fid}).json()
        assert 3 <= len(r["summary"]) <= 5
        assert len(r["citations"]) == len(r["summary"])
        assert all(c["filing_id"] == fid and c["section"] for c in r["citations"])
        assert all(len(b.split()) <= 20 for b in r["summary"])
    assert any("patent" in b.lower() or "infring" in b.lower()
               for b in api.post("/risksummary", json={"filing_id": "HLXR_2022"}).json()["summary"])


@pytest.mark.parametrize("n", [3, 4, 5])
def test_risksummary_bullet_count(api, n):
    assert len(api.post("/risksummary", json={"filing_id": "ACMR_2023", "max_bullets": n}).json()["summary"]) == n


def test_risksummary_errors(api):
    assert api.post("/risksummary", json={"filing_id": "NOPE_2020"}).status_code == 404
    assert api.post("/risksummary", json={"filing_id": "not an id"}).status_code == 422
    assert api.post("/risksummary", json={"filing_id": "ACMR_2023", "max_bullets": 9}).status_code == 422
    assert api.post("/qa", json={"question": "x"}).status_code == 422


def test_gateway_down_gives_503(make_api):
    api = make_api(fail=True)
    assert api.post("/qa", json={"question": "cybersecurity risks ACMR_2023"}).status_code == 503
    assert api.post("/risksummary", json={"filing_id": "ACMR_2023"}).status_code == 503
    assert api.get("/health").status_code == 503


def test_snippet_only_gateway_degrades_gracefully(make_api):
    """A gateway without `text` and without /doc/.../section (like the original kit) must not crash the app."""
    class R:
        def __init__(self, r, body=None, code=None):
            self._r, self._b, self.status_code, self.text = r, body, code or r.status_code, ""
        def json(self):
            return self._b if self._b is not None else self._r.json()

    def mutate(path, r):
        if path.startswith("/doc/") and "/section/" in path:
            return R(r, {}, 404)
        if path.startswith("/search"):
            b = r.json()
            for h in b["results"]:
                h.pop("text", None)
            return R(r, b)
        if path.startswith("/filings"):
            return R(r, {}, 404)
        return r
    api = make_api(mutate)
    assert "data breaches" in api.post("/qa", json={"question": "cybersecurity risks ACMR_2023"}).json()["answer"]
    assert api.post("/risksummary", json={"filing_id": "ACMR_2023"}).status_code == 200


def test_health_and_debug_retrieve(api):
    assert api.get("/health").json()["filings"] == 15
    hits = api.post("/debug/retrieve", json={"question": "gross margin", "filing_id": "ACMR_2023"}).json()
    assert hits[0] == {"filing_id": "ACMR_2023", "section": "Financials", "score": hits[0]["score"]}


def test_mock_server_hardening():
    from app.asgi_client import ASGIClient as TestClient
    from mock_server.main import app, load_filing_text
    c = TestClient(app)
    assert load_filing_text("../README") is None and load_filing_text("..\\x") is None
    assert c.get("/doc/nope").json()["exists"] is False
    assert len(c.get("/filings").json()["filings"]) == 15
