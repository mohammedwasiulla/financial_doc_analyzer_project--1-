"""Scripted walk-through for the 2-3 minute demo video (needs the two servers running)."""
import json, os, sys, time
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app.client import UrllibSession   # stdlib HTTP client: no `requests` import (can hang on some Windows setups)

APP = os.getenv("APP_BASE_URL", "http://127.0.0.1:9025")
S = UrllibSession()


def show(title, resp):
    print(f"\n=== {title}\n{json.dumps(resp, indent=2)}")
    time.sleep(float(os.getenv("DEMO_PAUSE", "1.5")))


def qa(q, fid=None):
    return S.post(f"{APP}/qa", json={"question": q, "filing_id": fid}, timeout=120).json()


def rs(fid):
    return S.post(f"{APP}/risksummary", json={"filing_id": fid}, timeout=120).json()


def main():
    print("health:", S.get(f"{APP}/health", timeout=20).json())
    show("1. Clause-level Q&A with citation", qa("What are the cybersecurity risks for ACMR-2023?"))
    show("2. Financial fact", qa("What was the gross margin for ZYNT 2023?"))
    show("3. Two filings compared", qa("How did ZYNT's gross margin change from 2022 to 2023?"))
    show("4. Low confidence -> I don't know", qa("What is the CEO's compensation at ACMR_2023?"))
    show("5. Partial match is flagged", qa("Does ACMR_2023 face supply chain risk from hurricanes?"))
    show("6. Risk summary (3-5 cited bullets)", rs("HLXR_2022"))
    r = S.post(f"{APP}/risksummary", json={"filing_id": "NOPE_2020"}, timeout=10)
    show(f"7. Unknown filing -> HTTP {r.status_code}", r.json())


if __name__ == "__main__":
    try:
        main()
    except OSError as e:
        sys.exit(f"Cannot reach the app at {APP} ({e}).\nStart BOTH servers first: mock (port 8030) and app (port 9025). See README.")
