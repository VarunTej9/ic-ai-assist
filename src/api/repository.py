from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Protocol

from .models import (
    Anomaly,
    AuditEvent,
    Evidence,
    ModelRecord,
    Recommendation,
)

class ModelRepository(Protocol):
    def get_model(
        self,
        model_id: str,
        tenant_id: str,
    ) -> ModelRecord | None:
        ...

    def get_recommendation(
        self,
        recommendation_id: str,
        tenant_id: str,
    ) -> Recommendation | None:
        ...

class SyntheticModelRepository:
    def __init__(self) -> None:
        now = datetime.now(timezone.utc)

        self.models: list[ModelRecord] = [
            ModelRecord(
                model_id="model-001",
                tenant_id="tenant-a",
                display_name="Balanced Growth Model",
                model_version="v1.4.2",
                description="Synthetic model used for Story 5 testing.",
                history=[
                    AuditEvent(
                        event_id="event-001",
                        model_id="model-001",
                        event_type="CREATED",
                        occurred_at=now - timedelta(days=5),
                        actor="system",
                        summary="Model created from synthetic configuration.",
                        model_version="v1.0.0",
                    ),
                    AuditEvent(
                        event_id="event-002",
                        model_id="model-001",
                        event_type="REBALANCED",
                        occurred_at=now - timedelta(days=2),
                        actor="analyst-001",
                        summary="Synthetic rebalance completed.",
                        model_version="v1.4.1",
                    ),
                    AuditEvent(
                        event_id="event-003",
                        model_id="model-001",
                        event_type="ANOMALY_REVIEWED",
                        occurred_at=now - timedelta(hours=4),
                        actor="analyst-001",
                        summary="Anomaly evidence opened for review.",
                        model_version="v1.4.2",
                    ),
                ],
                anomalies=[
                    Anomaly(
                        anomaly_id="anomaly-001",
                        model_id="model-001",
                        detected_at=now - timedelta(hours=5),
                        score=0.91,
                        reason_codes=[
                            "WEIGHT_DEVIATION",
                            "TURNOVER_SPIKE",
                        ],
                        model_version="v1.4.2",
                        severity="high",
                    ),
                    Anomaly(
                        anomaly_id="anomaly-002",
                        model_id="model-001",
                        detected_at=now - timedelta(days=1),
                        score=0.64,
                        reason_codes=[
                            "CONCENTRATION_CHANGE",
                        ],
                        model_version="v1.4.2",
                        severity="medium",
                    ),
                ],
                evidence=[
                    Evidence(
                        evidence_id="evidence-001",
                        title="Audit Runbook",
                        source="data/documents/audit_runbook.md",
                        section="Investigation",
                        document_version="1.0",
                        excerpt=(
                            "Investigate large weight deviations by "
                            "comparing the current model version with "
                            "the preceding approved version."
                        ),
                        relevance_score=0.95,
                    ),
                    Evidence(
                        evidence_id="evidence-002",
                        title="Audit Definitions",
                        source="data/documents/audit_definitions.md",
                        section="Anomaly Definitions",
                        document_version="1.0",
                        excerpt=(
                            "A turnover spike is a review signal. "
                            "It is not proof that an action is required."
                        ),
                        relevance_score=0.88,
                    ),
                ],
                recommendations=[
                    Recommendation(
                        recommendation_id="recommendation-001",
                        text=(
                            "Compare this event with the previous "
                            "approved model version."
                        ),
                        reason=(
                            "The event has a weight deviation and "
                            "turnover spike reason code."
                        ),
                    )
                ],
            ),
            ModelRecord(
                model_id="model-empty",
                tenant_id="tenant-a",
                display_name="Empty Results Model",
                model_version="v0.1.0",
                description="Synthetic model with no results.",
                history=[],
                anomalies=[],
                evidence=[],
                recommendations=[],
            ),
            ModelRecord(
                model_id="model-002",
                tenant_id="tenant-b",
                display_name="Tenant B Model",
                model_version="v2.0.0",
                description="Synthetic model belonging to another tenant.",
                history=[],
                anomalies=[],
                evidence=[],
                recommendations=[],
            ),
        ]

    def get_model(
        self,
        model_id: str,
        tenant_id: str,
    ) -> ModelRecord | None:
        return next(
            (
                model
                for model in self.models
                if model.model_id == model_id
                and model.tenant_id == tenant_id
            ),
            None,
        )

    def get_recommendation(
        self,
        recommendation_id: str,
        tenant_id: str,
    ) -> Recommendation | None:
        for model in self.models:
            if model.tenant_id != tenant_id:
                continue

            for recommendation in model.recommendations:
                if (
                    recommendation.recommendation_id
                    == recommendation_id
                ):
                    return recommendation

        return None
