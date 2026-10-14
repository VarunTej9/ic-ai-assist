from __future__ import annotations

import os

import requests
import streamlit as st

API_BASE_URL = os.getenv(
    "API_BASE_URL",
    "http://127.0.0.1:8000",
)

st.set_page_config(
    page_title="IC AI Assist",
    layout="wide",
)

st.title("IC AI Assist")
st.caption(
    "Read-only synthetic model investigation interface"
)

if "token" not in st.session_state:
    st.session_state.token = ""

st.sidebar.header("Local authorization")

user_id = st.sidebar.text_input(
    "User ID",
    value="user-001",
)

tenant_id = st.sidebar.text_input(
    "Tenant ID",
    value="tenant-a",
)

role = st.sidebar.selectbox(
    "Role",
    [
        "viewer",
        "investigator",
        "reviewer",
        "admin",
    ],
)

if st.sidebar.button("Create demo token"):
    response = requests.post(
        f"{API_BASE_URL}/api/v1/auth/demo-token",
        json={
            "user_id": user_id,
            "tenant_id": tenant_id,
            "role": role,
        },
        timeout=10,
    )

    if response.ok:
        st.session_state.token = response.json()[
            "data"
        ]["access_token"]

        st.sidebar.success("Token created.")
    else:
        st.sidebar.error(response.text)

token = st.sidebar.text_input(
    "Bearer token",
    value=st.session_state.token,
    type="password",
)

model_id = st.text_input(
    "Model ID",
    value="model-001",
)

headers = {
    "Authorization": f"Bearer {token}"
}

if st.button("Load investigation"):
    if not token:
        st.error("Create or enter a bearer token first.")
    else:
        history_response = requests.get(
            f"{API_BASE_URL}/api/v1/models/"
            f"{model_id}/history",
            headers=headers,
            timeout=10,
        )

        anomaly_response = requests.get(
            f"{API_BASE_URL}/api/v1/models/"
            f"{model_id}/anomalies",
            headers=headers,
            timeout=10,
        )

        if not history_response.ok:
            st.error(history_response.text)
        elif not anomaly_response.ok:
            st.error(anomaly_response.text)
        else:
            st.session_state.history = (
                history_response.json()["data"]
            )
            st.session_state.anomalies = (
                anomaly_response.json()["data"]
            )

if "history" in st.session_state:
    left, right = st.columns(2)

    with left:
        st.subheader("Audit timeline")

        events = st.session_state.history["events"]

        if not events:
            st.info("No audit events found.")

        for event in events:
            with st.container(border=True):
                st.write(
                    f"**{event['event_type']}** — "
                    f"{event['occurred_at']}"
                )
                st.write(event["summary"])
                st.caption(
                    f"Actor: {event['actor']} | "
                    f"Version: {event['model_version']}"
                )

    with right:
        st.subheader("Anomalies")

        anomalies = st.session_state.anomalies[
            "anomalies"
        ]

        if not anomalies:
            st.info("No anomalies found.")

        for anomaly in anomalies:
            with st.container(border=True):
                st.write(
                    f"**{anomaly['severity'].upper()}** "
                    f"score: {anomaly['score']}"
                )
                st.write(
                    "Reasons: "
                    + ", ".join(
                        anomaly["reason_codes"]
                    )
                )
                st.caption(
                    f"Model version: "
                    f"{anomaly['model_version']}"
                )

st.divider()

st.subheader("Evidence assistant")

question = st.text_input(
    "Ask a question",
    value="Why was this model flagged?",
)

if st.button("Ask assistant"):
    if not token:
        st.error("Create or enter a bearer token first.")
    else:
        response = requests.post(
            f"{API_BASE_URL}/api/v1/assistant/questions",
            headers=headers,
            json={
                "model_id": model_id,
                "question": question,
            },
            timeout=10,
        )

        if not response.ok:
            st.error(response.text)
        else:
            answer = response.json()["data"]

            st.subheader("Answer")
            st.write(answer["answer"])

            st.metric(
                "Confidence",
                answer["confidence"],
            )

            st.warning(answer["uncertainty"])

            st.subheader("Evidence")

            for evidence in answer["evidence"]:
                with st.container(border=True):
                    st.write(
                        f"**{evidence['title']}**"
                    )
                    st.write(evidence["excerpt"])
                    st.caption(
                        f"{evidence['source']} | "
                        f"Section: {evidence['section']}"
                    )

            recommendation = answer.get(
                "recommendation"
            )

            if recommendation:
                st.subheader(
                    "Recommended investigation step"
                )

                st.info(
                    recommendation["text"]
                )

                st.caption(
                    "Status: pending human review. "
                    "No action was executed."
                )

                feedback = st.selectbox(
                    "Feedback",
                    [
                        "useful",
                        "incorrect",
                        "needs_review",
                    ],
                )

                if st.button("Submit feedback"):
                    feedback_response = requests.post(
                        f"{API_BASE_URL}/api/v1/"
                        f"recommendations/"
                        f"{recommendation['recommendation_id']}"
                        f"/feedback",
                        headers=headers,
                        json={
                            "feedback_type": feedback
                        },
                        timeout=10,
                    )

                    if feedback_response.ok:
                        st.success(
                            "Feedback recorded."
                        )
                    else:
                        st.error(
                            feedback_response.text
                        )
