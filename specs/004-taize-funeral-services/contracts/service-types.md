# Contract: Service-Type Registry (config + classification)

This contract replaces 003's `service.sunday_cutoff`, `saturday_vigil_after`, `title_template` and `description_template` keys (research S1). `service.church_name` and `service.no_article_names` remain global, as in [003 config-additions](../../003-lectionary-service-metadata/contracts/config-additions.md).

```yaml
service_types:                       # ordered; first match wins within a precedence level
  - id: worship
    label: Sunday worship
    match:
      when: {weekday: sunday, before: "12:00"}       # 003 clarification 1
      saturday_vigil_after: "16:00"                   # 003 L7: uses Sunday's values
    lectionary: true
    title_template: [service-title, service-title-no-special]     # S3 fallbacks
    description_template: service-description
    visibility: public
    default_duration_minutes: 75

  - id: taize
    label: Taizé
    match:
      keywords: ["taize"]                             # accent/case-insensitive, whole word
    lectionary: false
    title_template: taize-title
    description_template: taize-description
    visibility: public
    default_duration_minutes: 65

  - id: funeral
    label: Funeral / memorial
    match:
      keywords: ["funeral", "memorial", "celebration of life"]
    lectionary: false
    title_template: [funeral-title, funeral-title-short, funeral-title-shortest]
    description_template: funeral-description
    visibility: unlisted
    visibility_source: instance_only                  # S4: only the event instance may change it
    default_duration_minutes: 60
    requires: [funeral.name]                          # S2
    announce: true                                    # S5: email link on create/change/cancel
    details:                                          # directive → template value
      name:      {directive: yt.name, from_title: true}
      wording:   {directive: yt.wording, default: Funeral}
      years:     {directive: yt.years}
      obituary:  {directive: yt.obituary, kind: url}
      memorials: {directive: yt.memorials}

  # `other` is implicit and always last: 002 behavior (calendar SUMMARY/notes or templates.default_*)
```

## Classification (pure; `service.classify`)

| Order | Rule | `type_reason` |
|---|---|---|
| 1 | `yt.type: <id>` on the instance, else on the series master. `yt.service: yes` is the same as `worship`, and `yt.service: no` is the same as `other`. | `directive` |
| 2 | The first type whose `match.keywords` matches the title (NFKD, accents stripped, casefold, whole word or phrase) | `keyword` |
| 3 | The first type whose `match.when` matches local weekday and time (+ worship's Saturday-vigil rule) | `rule` |
| 4 | `other` | `default` |

An unknown `yt.type` id is a validation error. The occurrence is `failed` with the reason `Unknown service type "<id>" (known: worship, taize, funeral)`.

## Option reference

| Key | Type | Default | Meaning |
|---|---|---|---|
| `id` | slug | (required) | Used in `yt.type`, the CLI `--type`, and the `occurrence.service_type` column |
| `match.keywords` | list[str] | `[]` | Title keywords or phrases |
| `match.when` | `{weekday, before?, after?}` | none | Day and time rule |
| `lectionary` | bool | false | Look up 003 lectionary values (`service.*` context) |
| `title_template` / `description_template` | str or list[str] | 002 defaults | A list means fallbacks tried in order until the title fits |
| `visibility` | public \| unlisted \| private | `defaults.visibility` | |
| `visibility_source` | `any` \| `instance_only` | `any` | `instance_only` ignores series-level and global visibility (S4) |
| `default_duration_minutes` | int | 60 | Used when the event has no end |
| `requires` | list[str] | `[]` | Context values that must be present, else `failed` (S2) |
| `announce` | bool | false | Email the link on create, change and cancel (S5) |
| `details` | map | `{}` | Per-type values from directives, exposed as `<id>.<key>` in templates |

## Validation (`config check`)

- Every `id` is unique. `other` is reserved.
- Every referenced template exists (in `templates.dir` or bundled).
- `requires` paths exist in `details` or in the standard context.
- At most one type has `lectionary: true` per matching day. This is a warning only.
