# Data Model: Service Types (migration `0004_service_type_details.sql`)

This extends [001](../001-youtube-livestream-scheduler/data-model.md) and [003](../003-lectionary-service-metadata/data-model.md). Service types themselves are configuration ([contracts/service-types.md](contracts/service-types.md)), not tables.

## occurrence (changes)

| Field | Type | Rules |
|---|---|---|
| service_type | TEXT NOT NULL DEFAULT 'other' | A registry id. *Added by 003's migration `0003`; listed here for completeness.* |
| type_reason | TEXT NOT NULL DEFAULT 'default' | `directive` \| `keyword` \| `rule` \| `default`. *Added by 003's migration `0003`.* |
| type_values_json | TEXT NULL | **(0004)** Per-type details, e.g. `{"name": "Jane Doe", "wording": "Funeral", "years": null, …}`, with a source per value |
| external_broadcast_id | TEXT NULL | Set only in `exists_external`. **Never** copied to `broadcast`. *Added by 001's migration `0001` (the guard ships with the 001 MVP).* |
| external_title / external_start_utc | TEXT NULL | As seen in the latest listing. *Added by 001's migration `0001`.* |
| announced_start_utc | TEXT NULL | **(0004)** Last start time announced by email (S5). Used to detect "changed". |

## Occurrence state machine (additions to 001)

```text
pending ── external livestream within ±15 min (S6) ──► exists_external
exists_external ── external livestream gone & start in future ──► pending
exists_external ── occurrence leaves calendar ──► cancelled   (no API call; nothing of ours to delete)
exists_external ── start passed ──► past
pending ── required value missing (e.g. funeral.name) ──► failed   (reason names the missing value)
failed ── calendar event edited so required value present ──► pending (via desired_hash change, 001)
```

`exists_external` is checked before any `create` in a run. It costs one `list_upcoming` call per run, and only when creates are planned or `exists_external` rows exist.

## Funeral visibility (S4)

The effective visibility is computed by the renderer and stored in `occurrence.visibility`. For `visibility_source: instance_only`, the inputs are only the type's `visibility` and an instance-level `yt.visibility`. The run log records `visibility_reason` (`type_default` or `instance_directive`) in `values_json`.

## notification (usage only, no schema change)

New `problem_key` families: `announce:<occ>:<kind>:<start_utc>` (one-shot, never re-sent) and `external:<occ>`. One-shot keys are marked resolved immediately after a successful send.
