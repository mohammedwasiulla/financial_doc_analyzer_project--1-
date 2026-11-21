from typing import List, Optional
from pydantic import BaseModel, Field, field_validator
from .text_utils import normalize_filing_id


class QAReq(BaseModel):
    question: str = Field(..., min_length=3, max_length=500, examples=["What are the cybersecurity risks for ACMR-2023?"])
    filing_id: Optional[str] = Field(None, description="Optional scope, e.g. ACMR_2023. Also parsed from the question.")

    @field_validator("filing_id")
    @classmethod
    def _norm(cls, v):
        if v is None or not v.strip():
            return None
        n = normalize_filing_id(v.strip())
        if not n:
            raise ValueError("filing_id must look like ACMR_2023")
        return n


class RiskReq(BaseModel):
    filing_id: str = Field(..., examples=["ACMR_2023"])
    max_bullets: Optional[int] = Field(None, ge=3, le=5, description="3-5 (default from RISK_BULLETS, 4)")

    @field_validator("filing_id")
    @classmethod
    def _norm(cls, v):
        n = normalize_filing_id(v.strip())
        if not n:
            raise ValueError("filing_id must look like ACMR_2023")
        return n


class Citation(BaseModel):
    filing_id: str
    section: str


class Evidence(BaseModel):
    filing_id: str
    section: str
    text: str


class QAResp(BaseModel):
    answer: str
    citations: List[Citation]
    confidence: float
    evidence: List[Evidence] = []
    note: Optional[str] = None


class RiskBullet(BaseModel):
    text: str
    topic: Optional[str] = None
    topic_label: Optional[str] = None
    section: str
    filing_id: str
    score: float


class RiskResp(BaseModel):
    filing_id: str
    summary: List[str]
    citations: List[Citation]
    bullets: List[RiskBullet]
    warning: Optional[str] = None


class RetrieveHit(BaseModel):
    filing_id: str
    section: str
    score: float
