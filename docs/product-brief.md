# IC AI Assist - Product Brief

## Problem

Investigating model and audit-history changes can require manually reviewing many records. This project demonstrates how an AI assistant can organize audit history, identify unusual events, answer questions from a knowledge base, and suggest safe investigation steps.

This is a personal learning project using synthetic data only.

## Goal

Build a read-only AI assistant that can:

- Display model audit history.
- Identify unusual audit events.
- Answer questions using synthetic documentation.
- Show evidence for every answer.
- Explain uncertainty.
- Recommend the next investigation step.
- Record user feedback.

## Target users

### Viewer

Can view audit history and assistant responses.

### Investigator

Can investigate unusual events and review evidence.

### Reviewer

Can approve, reject, or correct AI recommendations.

### Administrator

Can manage synthetic documents, evaluation data, and application configuration.

## In scope

- Synthetic model metadata.
- Synthetic audit-history data.
- Synthetic technical documentation.
- Rule-based anomaly detection.
- Machine-learning anomaly detection.
- Retrieval-augmented generation.
- Read-only REST API.
- Streamlit web interface.
- Human-reviewed recommendations.
- Evaluation and logging.

## Out of scope

- InvestCloud systems or repositories.
- Client or production data.
- Oracle, Snowflake, or SageMaker connections.
- Production writes.
- Automatic model changes.
- Investment advice.
- Automatic deployment.
- Autonomous agent actions.

## Success measures

- At least 25 evaluation questions are created.
- Every answer contains evidence or states that evidence is unavailable.
- Every anomaly contains a reason.
- The system does not modify data.
- The project runs locally from a clean setup.
- At least 80% of evaluation questions return relevant evidence.
- Unsupported questions are handled safely.

## Safe boundary

The application is read-only.

It can:

- Read synthetic audit data.
- Read synthetic documents.
- Calculate anomaly scores.
- Generate explanations.
- Store local feedback.

It cannot:

- Modify production systems.
- Modify model records.
- Send messages.
- Execute commands.
- Deploy software.
- Access InvestCloud or client data.

## AI response contract

Every assistant response must contain:

```json
{
  "answer": "Human-readable answer",
  "evidence": [
    {
      "source_id": "DOC-001",
      "title": "Synthetic Audit Guide",
      "content": "Relevant evidence"
    }
  ],
  "confidence": 0.85,
  "uncertainty": "No production data was used.",
  "model_version": "local-model-v1",
  "timestamp": "2026-09-19T10:00:00Z",
  "correlation_id": "query-0001"
}
