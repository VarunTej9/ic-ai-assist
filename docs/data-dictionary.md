

```markdown
# IC AI Assist - Data Dictionary

| Field | Type | Required | Description | Example |
|---|---|---:|---|---|
| event_id | integer | Yes | Unique audit-event identifier | 1001 |
| model_id | string | Yes | Synthetic model identifier | MODEL-001 |
| model_version | string | Yes | Version affected by the event | V1.2 |
| event_type | string | Yes | Type of model activity | MODEL_UPDATED |
| user_id | string | Yes | Synthetic user identifier | USER-101 |
| event_time | datetime | Yes | Time of the event in UTC | 2026-09-19T10:00:00Z |
| status | string | Yes | Event result | SUCCESS |
| change_count | integer | Yes | Number of changed fields | 3 |
| description | string | No | Synthetic event description | Updated model allocation |
| tenant_id | string | Yes | Synthetic tenant boundary | TENANT-001 |
| source | string | Yes | Data source name | synthetic_csv |
| batch_id | string | Yes | Ingestion batch identifier | BATCH-001 |

## Allowed event types

- MODEL_CREATED
- MODEL_UPDATED
- MODEL_DELETED
- MODEL_ASSIGNED
- MODEL_UNASSIGNED
- MODEL_RESTORED

## Allowed statuses

- SUCCESS
- FAILED
- REVERTED
- PENDING

## Data rules

- `event_id` must be unique.
- `model_id` cannot be empty.
- `event_time` must be stored in UTC.
- `change_count` cannot be negative.
- `user_id` must use synthetic identifiers.
- No email addresses, names, credentials, or client information are allowed.
