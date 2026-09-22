from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

MODEL_VERSION = "isolation-forest-v1"
FEATURE_VERSION = "audit-features-v1"
TRAINING_DATA_VERSION = "sqlite-audit-snapshot-v1"

FEATURE_COLUMNS = [
    "change_count",
    "is_failed",
    "is_reverted",
    "is_off_hours",
    "model_event_count",
    "user_model_event_count",
    "is_new_event_type",
]

def load_events_from_database(db_path: Path) -> pd.DataFrame:
    with sqlite3.connect(db_path) as connection:
        events = pd.read_sql_query(
            """
            SELECT
                event_id,
                model_id,
                event_type,
                user_id,
                event_time,
                status,
                change_count,
                tenant_id
            FROM audit_events
            ORDER BY event_id
            """,
            connection,
        )

    if events.empty:
        raise ValueError("No audit events were found in the database.")

    events["event_time"] = pd.to_datetime(
        events["event_time"],
        utc=True,
        errors="coerce",
    )

    return events

def build_features(events: pd.DataFrame) -> pd.DataFrame:
    features = pd.DataFrame(index=events.index)

    features["change_count"] = (
        pd.to_numeric(events["change_count"], errors="coerce")
        .fillna(0)
        .astype(float)
    )

    features["is_failed"] = (
        events["status"].astype(str).str.upper() == "FAILED"
    ).astype(int)

    features["is_reverted"] = (
        events["status"].astype(str).str.upper() == "REVERTED"
    ).astype(int)

    hours = events["event_time"].dt.hour

    features["is_off_hours"] = (
        (hours < 8) | (hours >= 18)
    ).astype(int)

    model_event_counts = events["model_id"].value_counts()

    features["model_event_count"] = (
        events["model_id"]
        .map(model_event_counts)
        .fillna(0)
        .astype(float)
    )

    user_model_key = (
        events["user_id"].astype(str)
        + "|"
        + events["model_id"].astype(str)
    )

    user_model_counts = user_model_key.value_counts()

    features["user_model_event_count"] = (
        user_model_key
        .map(user_model_counts)
        .fillna(0)
        .astype(float)
    )

    model_event_type_counts = (
        events.groupby(["model_id", "event_type"])
        .size()
        .rename("event_type_count")
        .reset_index()
    )

    events_with_counts = events.merge(
        model_event_type_counts,
        on=["model_id", "event_type"],
        how="left",
    )

    features["is_new_event_type"] = (
        events_with_counts["event_type_count"] == 1
    ).astype(int)

    return features[FEATURE_COLUMNS]

def calculate_rule_score(
    event: pd.Series,
    features: pd.Series,
) -> tuple[float, list[str]]:
    score = 0.0
    reasons: list[str] = []

    if features["change_count"] >= 10:
        score += 0.35
        reasons.append("Large number of changes in one event")

    if features["is_failed"] == 1:
        score += 0.25
        reasons.append("Event failed")

    if features["is_reverted"] == 1:
        score += 0.30
        reasons.append("Event was reverted")

    if features["is_off_hours"] == 1:
        score += 0.15
        reasons.append("Change occurred outside normal working hours")

    if features["is_new_event_type"] == 1:
        score += 0.15
        reasons.append("New event type for this model")

    if features["user_model_event_count"] == 1:
        score += 0.10
        reasons.append("Unusual user and model combination")

    return min(score, 1.0), reasons

def normalize_ml_scores(raw_scores: np.ndarray) -> np.ndarray:
    minimum = raw_scores.min()
    maximum = raw_scores.max()

    if maximum == minimum:
        return np.full(len(raw_scores), 0.5)

    return (raw_scores - minimum) / (maximum - minimum)

def get_risk_band(score: float) -> str:
    if score >= 0.75:
        return "HIGH"

    if score >= 0.45:
        return "MEDIUM"

    return "LOW"

def run_detection(
    events: pd.DataFrame,
    model_directory: Path,
) -> list[dict[str, Any]]:
    features = build_features(events)

    model = IsolationForest(
        n_estimators=200,
        contamination="auto",
        random_state=42,
    )

    model.fit(features[FEATURE_COLUMNS])

    model_directory.mkdir(parents=True, exist_ok=True)

    model_path = model_directory / f"{MODEL_VERSION}.joblib"
    joblib.dump(model, model_path)

    predictions = model.predict(features[FEATURE_COLUMNS])

    raw_ml_scores = -model.decision_function(
        features[FEATURE_COLUMNS]
    )

    ml_scores = normalize_ml_scores(raw_ml_scores)

    results: list[dict[str, Any]] = []

    for index, event in events.iterrows():
        rule_score, reasons = calculate_rule_score(
            event=event,
            features=features.loc[index],
        )

        ml_score = float(ml_scores[index])

        if predictions[index] == -1:
            reasons.append(
                "Isolation Forest detected an unusual feature combination"
            )

        if not reasons:
            reasons.append("No strong unusual signal detected")

        combined_score = round(
            min((rule_score * 0.60) + (ml_score * 0.40), 1.0),
            4,
        )

        results.append(
            {
                "event_id": int(event["event_id"]),
                "model_id": event["model_id"],
                "risk_score": combined_score,
                "risk_band": get_risk_band(combined_score),
                "rule_score": round(rule_score, 4),
                "ml_score": round(ml_score, 4),
                "is_unusual": bool(
                    combined_score >= 0.45 or predictions[index] == -1
                ),
                "reasons": reasons,
                "model_version": MODEL_VERSION,
                "training_data_version": TRAINING_DATA_VERSION,
                "feature_version": FEATURE_VERSION,
                "review_status": "PENDING",
                "reviewed_by": None,
                "review_reason": None,
            }
        )

    return results

def save_results(
    results: list[dict[str, Any]],
    output_path: Path,
) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    response = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model_version": MODEL_VERSION,
        "training_data_version": TRAINING_DATA_VERSION,
        "feature_version": FEATURE_VERSION,
        "results": results,
    }

    output_path.write_text(
        json.dumps(response, indent=2),
        encoding="utf-8",
    )

def review_result(
    output_path: Path,
    event_id: int,
    reviewer: str,
    status: str,
    reason: str,
) -> None:
    allowed_statuses = {
        "ACCEPTED",
        "REJECTED",
        "NEEDS_MORE_INFO",
    }

    if status not in allowed_statuses:
        raise ValueError(
            f"Status must be one of: {allowed_statuses}"
        )

    if not reason.strip():
        raise ValueError("A review reason is required.")

    response = json.loads(
        output_path.read_text(encoding="utf-8")
    )

    matching_result = None

    for result in response["results"]:
        if result["event_id"] == event_id:
            matching_result = result
            break

    if matching_result is None:
        raise ValueError(f"Event {event_id} was not found.")

    matching_result["review_status"] = status
    matching_result["reviewed_by"] = reviewer
    matching_result["review_reason"] = reason

    output_path.write_text(
        json.dumps(response, indent=2),
        encoding="utf-8",
    )

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run baseline audit anomaly detection."
    )

    parser.add_argument(
        "--db",
        default="data/processed/ic_ai_assist.db",
    )

    parser.add_argument(
        "--output",
        default="data/processed/anomaly_results.json",
    )

    parser.add_argument(
        "--model-directory",
        default="data/processed/models",
    )

    parser.add_argument("--review-event-id", type=int)
    parser.add_argument("--reviewer")
    parser.add_argument("--review-status")
    parser.add_argument("--review-reason")

    args = parser.parse_args()

    output_path = Path(args.output)

    if args.review_event_id is not None:
        review_result(
            output_path=output_path,
            event_id=args.review_event_id,
            reviewer=args.reviewer,
            status=args.review_status,
            reason=args.review_reason,
        )

        print(f"Review saved for event {args.review_event_id}")
        return

    events = load_events_from_database(Path(args.db))

    results = run_detection(
        events=events,
        model_directory=Path(args.model_directory),
    )

    save_results(
        results=results,
        output_path=output_path,
    )

    unusual_count = sum(
        1 for result in results if result["is_unusual"]
    )

    print(f"Processed events: {len(results)}")
    print(f"Unusual events: {unusual_count}")
    print(f"Results saved to: {output_path}")

if __name__ == "__main__":
    main()
