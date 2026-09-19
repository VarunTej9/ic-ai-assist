from pathlib import Path

import pandas as pd
import streamlit as st
from sklearn.ensemble import IsolationForest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_FILE = PROJECT_ROOT / "data" / "audit_events.csv"

st.set_page_config(
    page_title="IC AI Assist",
    page_icon="🤖",
    layout="wide",
)

st.title("IC AI Assist")
st.subheader("Governed APL Audit and Support Assistant")

if not DATA_FILE.exists():
    st.error(f"Data file not found: {DATA_FILE}")
    st.stop()

audit_data = pd.read_csv(DATA_FILE)

audit_data["event_time"] = pd.to_datetime(audit_data["event_time"])

st.write("### Audit history")
st.dataframe(audit_data, use_container_width=True)

st.write("### Unusual audit events")

features = audit_data[["change_count"]].copy()

model = IsolationForest(
    contamination=0.25,
    random_state=42,
)

predictions = model.fit_predict(features)

audit_data["anomaly"] = predictions == -1

anomalies = audit_data[audit_data["anomaly"]]

if anomalies.empty:
    st.success("No unusual events were detected.")
else:
    st.warning(f"{len(anomalies)} unusual event(s) detected.")
    st.dataframe(anomalies, use_container_width=True)

st.write("### Summary")

col1, col2, col3 = st.columns(3)

with col1:
    st.metric("Total events", len(audit_data))

with col2:
    st.metric("Successful events", int((audit_data["status"] == "SUCCESS").sum()))

with col3:
    st.metric("Unusual events", len(anomalies))
