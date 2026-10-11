---
document_id: DOC-002
title: Synthetic Audit Investigation Runbook
version: v1
tenant_id: TENANT-LOCAL
---

# Synthetic Audit Investigation Runbook

## Failed event investigation

When an event has FAILED status, first check the model ID, event time, change count, and related events for the same model.

## Reverted event investigation

When an event has REVERTED status, compare it with the previous successful event for the same model.

## Unusual event investigation

An unusual event should be reviewed by a human. Check the evidence and reason codes before deciding whether further investigation is needed.
