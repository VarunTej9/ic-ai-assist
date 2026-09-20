from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd
from pydantic import BaseModel, ConfigDict

REQUIRED_COLUMNS = [
    "event_id",
    "model_id",
    "event_type",
    "user_id",
    "event_time",
    "status",
    "change_count",
]

HASH_SALT = os.getenv("USER_HASH_SALT", "local-only-demo-salt")

class NormalizedAuditEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: int
    model_id: str
    model_version: str
    event_type: str
    user_id: str
    event_time: datetime
    status: str
    change_count: int
    description: str
    tenant_id: str
    source: str
    batch_id: str
    ingested_at: datetime

def is_missing(value: Any) -> bool:
    result = pd.isna(value)
    return bool(result) if not hasattr(result, "__len__") else False

def normalize_identifier(value: Any) -> str:
    return str(value).strip().upper()

def normalize_event_type(value: Any) -> str:
    text = str(value).strip().upper()
    return re.sub(r"[^A-Z0-9]+", "_", text).strip("_")

def normalize_status(value: Any) -> str:
    text = str(value).strip().upper()
    return re.sub(r"[^A-Z0-9]+", "_", text).strip("_")

def hash_user_id(user_id: Any) -> str:
    raw_value = f"{HASH_SALT}:{str(user_id).strip()}"
    return hashlib.sha256(raw_value.encode("utf-8")).hexdigest()[:16]

def read_input_file(input_path: Path) -> pd.DataFrame:
    if input_path.suffix.lower() == ".csv":
        return pd.read_csv(input_path)

    if input_path.suffix.lower() == ".json":
        with input_path.open("r", encoding="utf-8") as file:
            payload = json.load(file)

        if isinstance(payload, dict) and "records" in payload:
            payload = payload["records"]

        return pd.DataFrame(payload)

    raise ValueError("Only CSV and JSON files are supported.")

def normalize_row(
    row: pd.Series,
    source_name: str,
    batch_id: str,
    ingested_at: datetime,
) -> tuple[NormalizedAuditEvent | None, list[str]]:
    errors: list[str] = []

    for column in REQUIRED_COLUMNS:
        if column not in row or is_missing(row[column]):
            errors.append(f"Missing required field: {column}")

    if errors:
        return None, errors

    try:
        event_id = int(float(row["event_id"]))
    except (TypeError, ValueError):
        errors.append("event_id must be an integer")
        event_id = 0

    try:
        change_count = int(float(row["change_count"]))
        if change_count < 0:
            errors.append("change_count cannot be negative")
    except (TypeError, ValueError):
        errors.append("change_count must be a non-negative integer")
        change_count = 0

    event_time = pd.to_datetime(
        row["event_time"],
        utc=True,
        errors="coerce",
    )

    if pd.isna(event_time):
        errors.append("event_time must be a valid date/time")
        normalized_time = datetime.now(timezone.utc)
    else:
        normalized_time = event_time.to_pydatetime()

    if errors:
        return None, errors

    event = NormalizedAuditEvent(
        event_id=event_id,
        model_id=normalize_identifier(row["model_id"]),
        model_version=(
            "UNKNOWN"
            if "model_version" not in row or is_missing(row["model_version"])
            else normalize_identifier(row["model_version"])
        ),
        event_type=normalize_event_type(row["event_type"]),
        user_id=hash_user_id(row["user_id"]),
        event_time=normalized_time,
        status=normalize_status(row["status"]),
        change_count=change_count,
        description=(
            ""
            if "description" not in row or is_missing(row["description"])
            else str(row["description"]).strip()
        ),
        tenant_id=(
            "TENANT-LOCAL"
            if "tenant_id" not in row or is_missing(row["tenant_id"])
            else normalize_identifier(row["tenant_id"])
        ),
        source=source_name,
        batch_id=batch_id,
        ingested_at=ingested_at,
    )

    return event, []

def create_database(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)

    with sqlite3.connect(db_path) as connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_events (
                event_id INTEGER PRIMARY KEY,
                model_id TEXT NOT NULL,
                model_version TEXT NOT NULL,
                event_type TEXT NOT NULL,
                user_id TEXT NOT NULL,
                event_time TEXT NOT NULL,
                status TEXT NOT NULL,
                change_count INTEGER NOT NULL,
                description TEXT,
                tenant_id TEXT NOT NULL,
                source TEXT NOT NULL,
                batch_id TEXT NOT NULL,
                ingested_at TEXT NOT NULL
            )
            """
        )

        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS ingestion_runs (
                batch_id TEXT PRIMARY KEY,
                source TEXT NOT NULL,
                input_rows INTEGER NOT NULL,
                accepted_rows INTEGER NOT NULL,
                rejected_rows INTEGER NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )

def save_to_database(
    events: list[NormalizedAuditEvent],
    report: dict[str, Any],
    db_path: Path,
) -> None:
    create_database(db_path)

    with sqlite3.connect(db_path) as connection:
        for event in events:
            connection.execute(
                """
                INSERT OR REPLACE INTO audit_events (
                    event_id,
                    model_id,
                    model_version,
                    event_type,
                    user_id,
                    event_time,
                    status,
                    change_count,
                    description,
                    tenant_id,
                    source,
                    batch_id,
                    ingested_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    event.event_id,
                    event.model_id,
                    event.model_version,
                    event.event_type,
                    event.user_id,
                    event.event_time.isoformat(),
                    event.status,
                    event.change_count,
                    event.description,
                    event.tenant_id,
                    event.source,
                    event.batch_id,
                    event.ingested_at.isoformat(),
                ),
            )

        connection.execute(
            """
            INSERT OR REPLACE INTO ingestion_runs (
                batch_id,
                source,
                input_rows,
                accepted_rows,
                rejected_rows,
                created_at
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                report["batch_id"],
                report["source"],
                report["input_rows"],
                report["accepted_rows"],
                report["rejected_rows"],
                report["ingested_at"],
            ),
        )

def ingest_file(
    input_path: Path,
    db_path: Path,
    report_path: Path,
    batch_id: str,
) -> dict[str, Any]:
    dataframe = read_input_file(input_path)
    ingested_at = datetime.now(timezone.utc)

    accepted_events: list[NormalizedAuditEvent] = []
    rejected_rows: list[dict[str, Any]] = []
    seen_event_ids: set[int] = set()

    for row_number, (_, row) in enumerate(dataframe.iterrows(), start=2):
        event, errors = normalize_row(
            row=row,
            source_name=input_path.name,
            batch_id=batch_id,
            ingested_at=ingested_at,
        )

        if event is not None:
            if event.event_id in seen_event_ids:
                rejected_rows.append(
                    {
                        "row_number": row_number,
                        "errors": ["Duplicate event_id"],
                    }
                )
            else:
                seen_event_ids.add(event.event_id)
                accepted_events.append(event)
        else:
            rejected_rows.append(
                {
                    "row_number": row_number,
                    "errors": errors,
                }
            )

    normalized_records = [
        event.model_dump(exclude={"ingested_at"})
        for event in accepted_events
    ]

    for record in normalized_records:
        record["event_time"] = record["event_time"].isoformat()

    normalized_hash = hashlib.sha256(
        json.dumps(
            normalized_records,
            sort_keys=True,
            default=str,
        ).encode("utf-8")
    ).hexdigest()

    missing_values = {
        column: int(dataframe[column].isna().sum())
        for column in dataframe.columns
        if int(dataframe[column].isna().sum()) > 0
    }

    report = {
        "batch_id": batch_id,
        "source": input_path.name,
        "input_rows": len(dataframe),
        "accepted_rows": len(accepted_events),
        "rejected_rows": len(rejected_rows),
        "missing_values": missing_values,
        "rejected_details": rejected_rows,
        "normalized_records_hash": normalized_hash,
        "ingested_at": ingested_at.isoformat(),
    }

    save_to_database(
        events=accepted_events,
        report=report,
        db_path=db_path,
    )

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, indent=2),
        encoding="utf-8",
    )

    return report

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Normalize synthetic audit data into SQLite."
    )

    parser.add_argument("--input", required=True)
    parser.add_argument(
        "--db",
        default="data/processed/ic_ai_assist.db",
    )
    parser.add_argument(
        "--report",
        default="data/processed/quality_report.json",
    )
    parser.add_argument(
        "--batch-id",
        default="batch-local-001",
    )

    args = parser.parse_args()

    report = ingest_file(
        input_path=Path(args.input),
        db_path=Path(args.db),
        report_path=Path(args.report),
        batch_id=args.batch_id,
    )

    print(json.dumps(report, indent=2))

if __name__ == "__main__":
    main()
