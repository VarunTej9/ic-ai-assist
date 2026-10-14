from __future__ import annotations

from datetime import datetime
from typing import Generic, Literal, TypeVar

from pydantic import BaseModel, Field

T = TypeVar("T")

class ApiResponse(BaseModel, Generic[T]):
    data: T
    correlation_id: str

class ApiErrorResponse(BaseModel):
    code: str
    message: str
    correlation_id: str

class AuditEvent(BaseModel):
    event_id: str
    model_id: str
    event_type: str
    occurred_at: datetime
    actor: str
    summary: str
    model_version: str

class Anomaly(BaseModel):
    anomaly_id: str
    model_id: str
    detected_at: datetime
    score: float = Field(ge=0, le=1)
    reason_codes: list[str]
    model_version: str
    severity: Literal["low", "medium", "high"]

class Evidence(BaseModel):
    evidence_id: str
    title: str
    source: str
    section: str
    document_version: str
    excerpt: str
    relevance_score: float = Field(ge=0, le=1)

class Recommendation(BaseModel):
    recommendation_id: str
    text: str
    reason: str
    status: Literal["pending_review"] = "pending_review"

class ModelRecord(BaseModel):
    model_id: str
    tenant_id: str
    display_name: str
    model_version: str
    description: str
    history: list[AuditEvent]
    anomalies: list[Anomaly]
    evidence: list[Evidence]
    recommendations: list[Recommendation]

class ModelHistoryResponse(BaseModel):
    model_id: str
    model_version: str
    events: list[AuditEvent]

class ModelAnomaliesResponse(BaseModel):
    model_id: str
    anomalies: list[Anomaly]

class AskQuestionRequest(BaseModel):
    model_id: str = Field(min_length=1)
    question: str = Field(min_length=3, max_length=1000)

class AssistantAnswerResponse(BaseModel):
    model_id: str
    answer: str
    evidence: list[Evidence]
    confidence: float = Field(ge=0, le=1)
    uncertainty: str
    provider: str
    provider_version: str
    recommendation: Recommendation | None
    generated_at: datetime

class FeedbackRequest(BaseModel):
    feedback_type: Literal["useful", "incorrect", "needs_review"]
    comment: str | None = Field(default=None, max_length=2000)

class FeedbackResponse(BaseModel):
    feedback_id: str
    recommendation_id: str
    feedback_type: str
    created_at: datetime
    message: str

class DemoTokenRequest(BaseModel):
    user_id: str = Field(min_length=1)
    tenant_id: str = Field(min_length=1)
    role: Literal["viewer", "investigator", "reviewer", "admin"]

class DemoTokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_seconds: int
