from typing import List, Optional

from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: str = Field(..., description="'user' or 'assistant'")
    content: str = Field(..., max_length=20000)


class QueryRequest(BaseModel):
    doc_id: str = Field(..., description="UUID of the ingested document")
    question: str = Field(..., min_length=1, max_length=2000)
    chat_history: Optional[List[ChatMessage]] = None


class SourceSnippet(BaseModel):
    text: str
    chunk_index: int
    score: float


class QueryResponse(BaseModel):
    answer: str
    sources: List[SourceSnippet] = []
    engine: str = "none"


class RiskFlag(BaseModel):
    clause_type: str
    risk_level: str = Field(..., description="low | medium | high")
    plain_english: str
    concerns: List[str] = []
    chunk_index: int
    raw_text: str
    evidence: Optional[str] = None
    suggested_rewrite: Optional[str] = None
    negotiation_tip: Optional[str] = None
    severity_score: Optional[int] = Field(default=None, description="1 (minor) to 10 (critical)")
    analysis_source: str = "rules"


class RiskSummary(BaseModel):
    high: int = 0
    medium: int = 0
    low: int = 0
    overall_score: int = Field(0, description="0-100")
    overall_label: str = "LOW"


class RiskAnalysisResponse(BaseModel):
    doc_id: str
    filename: str = ""
    flags: List[RiskFlag] = []
    summary: RiskSummary
    engine: str = "rules"
    disclaimer: str = ""
