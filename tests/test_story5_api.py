from fastapi.testclient import TestClient

from src.api.main import app

client = TestClient(app)

def create_token(
    tenant_id: str = "tenant-a",
    role: str = "investigator",
) -> str:
    response = client.post(
        "/api/v1/auth/demo-token",
        json={
            "user_id": "test-user",
            "tenant_id": tenant_id,
            "role": role,
        },
    )

    assert response.status_code == 200

    return response.json()["data"]["access_token"]

def auth_headers(
    tenant_id: str = "tenant-a",
    role: str = "investigator",
) -> dict[str, str]:
    return {
        "Authorization": f"Bearer "
        f"{create_token(tenant_id, role)}"
    }

def test_authorized_user_can_read_history():
    response = client.get(
        "/api/v1/models/model-001/history",
        headers=auth_headers(),
    )

    assert response.status_code == 200

    body = response.json()

    assert body["data"]["model_id"] == "model-001"
    assert len(body["data"]["events"]) > 0
    assert "correlation_id" in body
    assert "X-Correlation-ID" in response.headers

def test_unauthenticated_user_is_rejected():
    response = client.get(
        "/api/v1/models/model-001/history"
    )

    assert response.status_code == 401
    assert response.json()["code"] == (
        "AUTHENTICATION_REQUIRED"
    )

def test_wrong_tenant_cannot_read_model():
    response = client.get(
        "/api/v1/models/model-001/history",
        headers=auth_headers(tenant_id="tenant-b"),
    )

    assert response.status_code == 404
    assert response.json()["code"] == "MODEL_NOT_FOUND"

def test_empty_anomalies_return_empty_array():
    response = client.get(
        "/api/v1/models/model-empty/anomalies",
        headers=auth_headers(),
    )

    assert response.status_code == 200
    assert response.json()["data"]["anomalies"] == []

def test_invalid_model_id_returns_safe_error():
    response = client.get(
        "/api/v1/models/not-real/history",
        headers=auth_headers(),
    )

    assert response.status_code == 404

    body = response.json()

    assert body["code"] == "MODEL_NOT_FOUND"
    assert "Traceback" not in body["message"]
    assert "secret" not in body["message"].lower()

def test_assistant_returns_evidence_and_uncertainty():
    response = client.post(
        "/api/v1/assistant/questions",
        headers=auth_headers(),
        json={
            "model_id": "model-001",
            "question": "Why was this model flagged?",
        },
    )

    assert response.status_code == 200

    data = response.json()["data"]

    assert data["answer"]
    assert len(data["evidence"]) > 0
    assert data["confidence"] >= 0
    assert data["uncertainty"]
    assert data["provider_version"]

def test_viewer_cannot_submit_feedback():
    response = client.post(
        "/api/v1/recommendations/"
        "recommendation-001/feedback",
        headers=auth_headers(role="viewer"),
        json={
            "feedback_type": "useful",
        },
    )

    assert response.status_code == 403
    assert response.json()["code"] == "FORBIDDEN"

def test_feedback_is_recorded_without_executing_action():
    response = client.post(
        "/api/v1/recommendations/"
        "recommendation-001/feedback",
        headers=auth_headers(role="reviewer"),
        json={
            "feedback_type": "needs_review",
        },
    )

    assert response.status_code == 200

    data = response.json()["data"]

    assert data["feedback_type"] == "needs_review"
    assert "No recommendation action was executed" in (
        data["message"]
    )

def test_openapi_contains_required_endpoints():
    response = client.get("/openapi.json")

    assert response.status_code == 200

    document = response.json()
    paths = document["paths"]

    assert "/api/v1/models/{model_id}/history" in paths
    assert "/api/v1/models/{model_id}/anomalies" in paths
    assert "/api/v1/assistant/questions" in paths
    assert (
        "/api/v1/recommendations/"
        "{recommendation_id}/feedback"
        in paths
    )

def test_downstream_failures_are_safe():
    class FailingRagBackend:
        def search(self, question, model):
            raise RuntimeError("Synthetic downstream failure")

    from src.api.services import AssistantService

    app.state.assistant_service = AssistantService(
        repository=app.state.repository,
        rag_backend=FailingRagBackend(),
    )

    response = client.post(
        "/api/v1/assistant/questions",
        headers=auth_headers(),
        json={
            "model_id": "model-001",
            "question": "Why was this model flagged?",
        },
    )

    assert response.status_code == 503

    body = response.json()

    assert body["code"] == (
        "DOWNSTREAM_SERVICE_UNAVAILABLE"
    )
    assert "Synthetic downstream failure" not in str(body)
