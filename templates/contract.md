---
title: {{title}}
labels: [architecture, contract]
confluence:
  page_id:
  version:
  synced_commit:
  synced_at:
  body_sha:
---

## Overview

Producer, consumers, transport (topic / queue / webhook), delivery guarantee
(at-least-once, ordering key), retention.

## Schema

```json
{
  "eventId": "uuid",
  "type": "example.created",
  "version": 1,
  "occurredAt": "2026-01-01T00:00:00Z",
  "payload": {}
}
```

| Field | Type | Required | Semantics |
| --- | --- | --- | --- |
| eventId | uuid | yes | unique per event, dedupe key |
| type | string | yes | |
| version | int | yes | schema version, see compatibility |

## Compatibility rules

:::warning
Additive changes only within a major version. Removing or renaming a field,
changing a type, or changing semantics requires a new `version` and a
parallel-run period.
:::

## Examples

```json
{}
```

## Consumers

| Consumer | Owner | Reads fields | Tolerates unknown fields |
| --- | --- | --- | --- |

## Related
