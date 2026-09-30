---
title: {{title}}
labels: [architecture, sequence]
confluence:
  page_id:
  version:
  synced_commit:
  synced_at:
  body_sha:
---

## Purpose

One paragraph: which business flow this covers, what triggers it, what
"done" means.

## Actors

| Actor | Role in this flow | Owner |
| --- | --- | --- |
| Client | | |
| Service A | | |

## Sequence

```mermaid
sequenceDiagram
    autonumber
    participant C as Client
    participant A as Service A
    C->>A: POST /example
    A-->>C: 201 Created
```

## Steps

| # | From → To | Message | Contract | Notes / failure handling |
| --- | --- | --- | --- | --- |
| 1 | Client → Service A | POST /example | [Example API](api-example.md) | |

## Failure modes

| Failure | Detected at step | Behaviour | Retry / compensation |
| --- | --- | --- | --- |

## Related

- Jira:
- Decisions:
