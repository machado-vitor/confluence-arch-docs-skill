---
title: {{title}}
labels: [architecture, context]
confluence:
  page_id:
  version:
  synced_commit:
  synced_at:
  body_sha:
---

## Responsibility

What this system owns, in two sentences. What it explicitly does not own.

## Context diagram

```mermaid
flowchart LR
    U[User] --> S[This system]
    S --> D[(Database)]
    S --> X[External service]
```

## Dependencies

| Dependency | Direction | Protocol | Contract | Failure impact |
| --- | --- | --- | --- | --- |

## Key flows

- [Flow name](sequence-flow.md)

## Decisions

- [ADR-0001](adr/0001-example.md)
