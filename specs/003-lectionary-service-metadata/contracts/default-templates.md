# Contract: Bundled Minnehaha UMC Templates (exact output)

These templates ship inside the package under `defaults/templates/`. An owner overrides one by placing a file with the same name in `templates.dir`. Their output is the acceptance oracle for 003 US1-1..3 and SC-001a. All files are `.txt.j2`, so whitespace is preserved exactly (research T2).

## `service-title.txt.j2`

```jinja
{{ date_long }} - {{ service.label }}{% if title_suffix %} {{ title_suffix }}{% endif %}
```

## `service-description.txt.j2`

```jinja
Welcome to {{ service.church_name }} on {{ date_long }} for {{ service.article }}{{ service.label }}!

{% include "snippets/minnehaha-footer.txt.j2" %}
```

## `snippets/minnehaha-footer.txt.j2`

Exact bytes matter here. Line 1 has **two** spaces after `you.`, and the line ending in `at:` keeps its **trailing space**. Both are copied from the live descriptions.

```text
Peace and good health to you.  The bulletin for the current service is available at: https://minnehaha.org/documents/Bulletin.pdf

News and other information also available at: 
https://www.minnehaha.org
https://www.facebook.com/MinnehahaUMC/
https://www.instagram.com/minnehahaumc/

Permission to podcast/stream the music in this service obtained from:
ONE LICENSE, License: A-711192
CCLI License: 3175826
CCS License: 11563
All rights reserved.
```

> **004 update**: this snippet is now composed of three parts (`snippets/bulletin`, `snippets/links`, `snippets/licensing`) with byte-identical output. See [004 templates](../../004-taize-funeral-services/contracts/templates.md#footer-parts-s7).

## Expected renders

| Date | Title | Description line 1 |
|---|---|---|
| 2026-09-27 | `September 27th, 2026 - Eighteenth Sunday after Pentecost` | `Welcome to Minnehaha United Methodist Church on September 27th, 2026 for the Eighteenth Sunday after Pentecost!` |
| 2026-10-04 | `October 4th, 2026 - Nineteenth Sunday after Pentecost` | `… on October 4th, 2026 for the Nineteenth Sunday after Pentecost!` (the live video has lower-case "nineteenth": the one documented difference) |
| 2026-10-18 | `October 18th, 2026 - Twenty-First Sunday after Pentecost` | `… on October 18th, 2026 for the Twenty-First Sunday after Pentecost!` |
| 2026-11-01 | `November 1st, 2026 - Twenty-Third Sunday after Pentecost (All Saints Sunday)` | `… for the Twenty-Third Sunday after Pentecost (All Saints Sunday)!` |
| 2026-11-22 | `November 22nd, 2026 - Twenty-Sixth Sunday after Pentecost (Reign of Christ / Christ the King Sunday)` (100 chars, within the 100 limit) | same label |
| 2026-05-24 | `May 24th, 2026 - Pentecost` | `… on May 24th, 2026 for Pentecost!` |
| 2026-04-05 + `yt.title-suffix: with the band` | `April 5th, 2026 - Easter Sunday with the band` | `… on April 5th, 2026 for Easter Sunday!` |
| 2026-12-24 (opted-in evening service) | `December 24th, 2026 - Christmas Eve` | `… on December 24th, 2026 for Christmas Eve!` (no article, see note) |

**Note**: "for the Christmas Eve" would read awkwardly. The bundled description template therefore uses `for {{ service.article }}{{ service.label }}`, where `article` is `"the "` for every computed name except a configurable list of names that take no article (default: `Pentecost`, `Christmas Eve`, `Christmas Day`, `Easter Sunday`, `Ash Wednesday`, `Maundy Thursday`, `Good Friday`, `Holy Saturday`, `Palm / Passion Sunday`, `Trinity Sunday`, `Transfiguration Sunday`). It is exposed as `service.article`. Sunday-after renders are unaffected, so SC-001a still holds.

The description after line 1 is identical for every date.
