from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Protocol
from uuid import uuid4

from .models import (
    AskQuestionRequest,
    AssistantAnswerResponse,
    FeedbackRequest,
    FeedbackResponse,
    ModelAnomaliesResponse,
    ModelHistoryResponse,
    ModelRecord,
)
from .repository import ModelRepository

class ModelNotFoundError(Exception):
    pass

class RecommendationNotFoundError(Exception):
    pass

class DownstreamServiceError(Exception):
    pass

class RagBackend(Protocol):
    def search(
        self,
        question: str,
        model: ModelRecord,
    ) -> list:
        ...

class LocalRagBackend:
    """
    Small deterministic RAG-style backend for synthetic data.

    Replace this class with an adapter around the existing
    src/rag_service.py implementation when its exact function
    signature is available.
    """

    def search(
        self,
        question: str,
        model: ModelRecord,
    ) -> list:
        question_words = set(
            re.findall(r"[a-zA-Z0-9_]+", question.lower())
        )

        ranked = []

        for evidence in model.evidence:
            evidence_words = set(
                re.findall(
                    r"[a-zA-Z0-9_]+",
                    (
                        evidence.title
                        + " "
                        + evidence.excerpt
                    ).lower(),
                )
            )

            overlap = question_words.intersection(evidence_words)

            score = (
                len(overlap) / max(len(question_words), 1)
            )

            score = max(
                score,
                evidence.relevance_score * 0.5,
            )

            ranked.append(
                evidence.model_copy(
                    update={
                        "relevance_score": round(
                            min(score, 1.0),
                            3,
                        )
                    }
                )
            )

        return sorted(
            ranked,
            key=lambda item: item.relevance_score,
            reverse=True,
        )[:3]

class InvestigationService:
    def __init__(self, repository: ModelRepository) -> None:
        self.repository = repository

    def _get_model(
        self,
        model_id: str,
        tenant_id: str,
    ) -> ModelRecord:
        model = self.repository.get_model(
            model_id=model_id,
            tenant_id=tenant_id,
        )

        if model is None:
            raise ModelNotFoundError()

        return model

    def get_history(
        self,
        model_id: str,
        tenant_id: str,
    ) -> ModelHistoryResponse:
        model = self._get_model(model_id, tenant_id)

        events = sorted(
            model.history,
            key=lambda event: event.occurred_at,
        )

        return ModelHistoryResponse(
            model_id=model.model_id,
            model_version=model.model_version,
            events=events,
        )

    def get_anomalies(
        self,
        model_id: str,
        tenant_id: str,
    ) -> ModelAnomaliesResponse:
        model = self._get_model(model_id, tenant_id)

        anomalies = sorted(
            model.anomalies,
            key=lambda anomaly: anomaly.detected_at,
            reverse=True,
        )

        return ModelAnomaliesResponse(
            model_id=model.model_id,
            anomalies=anomalies,
        )

class AssistantService:
    def __init__(
        self,
        repository: ModelRepository,
        rag_backend: RagBackend,
    ) -> None:
        self.repository = repository
        self.rag_backend = rag_backend

    def ask(
        self,
        request: AskQuestionRequest,
        tenant_id: str,
    ) -> AssistantAnswerResponse:
        model = self.repository.get_model(
            model_id=request.model_id,
            tenant_id=tenant_id,
        )

        if model is None:
            raise ModelNotFoundError()

        try:
            evidence = self.rag_backend.search(
                question=request.question,
                model=model,
            )
        except Exception as exc:
            raise DownstreamServiceError() from exc

        recommendation = (
            model.recommendations[0]
            if model.recommendations
            else None
        )

        if not evidence:
            return AssistantAnswerResponse(
                model_id=model.model_id,
                answer=(
                    "Insufficient evidence was found to answer "
                    "this question safely."
                ),
                evidence=[],
                confidence=0.1,
                uncertainty=(
                    "High uncertainty because no supporting "
                    "evidence was retrieved."
                ),
                provider="local-rag",
                provider_version="story5-local-rag-v1",
                recommendation=None,
                generated_at=datetime.now(timezone.utc),
            )

        return AssistantAnswerResponse(
            model_id=model.model_id,
            answer=(
                "The available evidence indicates that the "
                "model should be investigated by comparing the "
                "current version with the previous approved "
                "version. No action was executed."
            ),
            evidence=evidence,
            confidence=0.78,
            uncertainty=(
                "This answer is based only on synthetic retrieved "
                "evidence and is not an approval decision."
            ),
            provider="local-rag",
            provider_version="story5-local-rag-v1",
            recommendation=recommendation,
            generated_at=datetime.now(timezone.utc),
        )

class FeedbackService:
    def __init__(
        self,
        repository: ModelRepository,
    ) -> None:
        self.repository = repository
        self.feedback: list[dict] = []

    def add_feedback(
        self,
        recommendation_id: str,
        request: FeedbackRequest,
        user_id: str,
        tenant_id: str,
    ) -> FeedbackResponse:
        recommendation = self.repository.get_recommendation(
            recommendation_id=recommendation_id,
            tenant_id=tenant_id,
        )

        if recommendation is None:
            raise RecommendationNotFoundError()

        created_at = datetime.now(timezone.utc)

        self.feedback.append(
            {
                "feedback_id": str(uuid4()),
                "recommendation_id": recommendation_id,
                "feedback_type": request.feedback_type,
                "comment": request.comment,
                "user_id": user_id,
                "tenant_id": tenant_id,
                "created_at": created_at.isoformat(),
            }
        )

        return FeedbackResponse(
            feedback_id=self.feedback[-1]["feedback_id"],
            recommendation_id=recommendation_id,
            feedback_type=request.feedback_type,
            created_at=created_at,
            message=(
                "Feedback recorded. No recommendation action "
                "was executed."
            ),
        )
