---
title: {{title}}
labels: [architecture, api]
confluence:
  page_id:
  version:
  synced_commit:
  synced_at:
  body_sha:
---

## Overview

What this API is for, who calls it, base URL per environment, auth scheme.

:::info
Source of truth for the contract is `openapi.yaml` in the service repo. This
page is the human-readable view; on conflict, the spec wins.
:::

## Endpoints

| Method | Path | Auth | Idempotent | Purpose |
| --- | --- | --- | --- | --- |
| POST | /v1/example | bearer | yes (Idempotency-Key) | |

## POST /v1/example

### Request

```json
{
  "id": "string"
}
```

| Field | Type | Required | Semantics |
| --- | --- | --- | --- |
| id | string | yes | |

### Response 201

```json
{
  "id": "string",
  "status": "CREATED"
}
```

### Errors

| Status | Code | When | Retry |
| --- | --- | --- | --- |
| 400 | VALIDATION_ERROR | body fails schema | no |
| 409 | DUPLICATE | idempotency key reused with different body | no |
| 503 | UPSTREAM_UNAVAILABLE | dependency down | yes, backoff |

## Versioning

How breaking changes are introduced, deprecation window, header/path policy.

## Related

- Sequence:
- Contracts:
- Jira:
