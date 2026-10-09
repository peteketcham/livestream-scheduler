# Contract: Config Additions (extends 001 [config-schema.md](../../001-youtube-livestream-scheduler/contracts/config-schema.md))

```yaml
templates:                          # feature 002
  dir: ~/.config/livestream-scheduler/templates   # optional; bundled defaults used for missing files
  default_title: null               # null = calendar SUMMARY (002 FR-014)
  default_description: null         # null = calendar notes
  vars: {}                          # global custom values → {{ vars.* }}

# NOTE (004): sunday_cutoff, saturday_vigil_after, title_template, description_template move to
# service_types[worship] — see specs/004-taize-funeral-services/contracts/service-types.md.
service:                            # feature 003
  church_name: Minnehaha United Methodist Church
  sunday_cutoff: "12:00"            # Sunday events starting before this are services (clarification 1)
  saturday_vigil_after: "16:00"     # Saturday services at/after this use Sunday's values
  title_template: service-title     # bundled default (contracts/default-templates.md)
  description_template: service-description
  no_article_names: [Pentecost, Christmas Eve, Christmas Day, Easter Sunday, Ash Wednesday,
                     Maundy Thursday, Good Friday, Holy Saturday, Palm / Passion Sunday,
                     Trinity Sunday, Transfiguration Sunday]

lectionary:
  enabled: true
  listing_url: https://www.umcdiscipleship.org/calendar/lectionary
  special_days:                     # research L2; replaces defaults when set
    - {name: All Saints Sunday, first_sunday_of: november}
    - {name: "Reign of Christ / Christ the King Sunday", sunday_before: advent}
  name_aliases:                     # church naming preferences (liturgical-calendar.md)
    "Day of Pentecost": "Pentecost"
    "Trinity Sunday": "First Sunday after Pentecost"
  use_site_special_names: false
  allow_prose: false                # FR-010; true exposes service.summary + service.credit
  contact: null                     # optional; appended to User-Agent (owner's email is never sent by default)
  refresh_hours: 24
```

## Validation

| Rule | Message (example) |
|---|---|
| Every template named in config exists (in `templates.dir` or bundled) | `service.title_template: template "service-titel" not found` |
| `sunday_cutoff`, `saturday_vigil_after` are `HH:MM` | |
| Each `special_days` entry has `name` and exactly one rule key | `lectionary.special_days[2]: expected exactly one of first_sunday_of, nth_sunday, sunday_before, fixed, easter_offset, pentecost_offset` |
| `listing_url` is `https://www.umcdiscipleship.org/…` | Other hosts are out of scope (spec Assumptions) |

## Calendar directives added (extends 001 [calendar-mapping.md](../../001-youtube-livestream-scheduler/contracts/calendar-mapping.md))

| Directive | Values | Effect |
|---|---|---|
| `yt.service` | yes \| no | Force church-service on/off (beats the Sunday rule) |
| `yt.template` / `yt.title-template` | template name | Choose templates for this event or series |
| `yt.title` | text | Verbatim title (skips the title template) |
| `yt.title-suffix` | text | Appended to the label, e.g. `with the band`, giving `April 5th, 2026 - Easter Sunday with the band` |
| `yt.description` | `verbatim` | Use the calendar notes as the description (skips the template) |
| `yt.var.<name>` | text | Sets `vars.<name>` |
| `yt.day-name`, `yt.special`, `yt.readings`, `yt.series`, `yt.week-title` | text (`;`-lists) | Override service values (research L8) |
