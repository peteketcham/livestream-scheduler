# Contract: Bundled Taizé, Funeral and Footer Templates (exact output)

These extend [003 default-templates](../../003-lectionary-service-metadata/contracts/default-templates.md). All files are `.txt.j2` (whitespace preserved). Template context names are from [003 template-values](../../003-lectionary-service-metadata/contracts/template-values.md), plus `date_short` (`Oct 23, 2026`) and the per-type `funeral.*` values ([service-types.md](service-types.md)).

## Footer parts (S7)

`snippets/bulletin.txt.j2`:
```text
Peace and good health to you.  The bulletin for the current service is available at: https://minnehaha.org/documents/Bulletin.pdf
```

`snippets/links.txt.j2` (line 1 keeps its trailing space):
```text
News and other information also available at: 
https://www.minnehaha.org
https://www.facebook.com/MinnehahaUMC/
https://www.instagram.com/minnehahaumc/
```

`snippets/licensing.txt.j2`:
```text
Permission to podcast/stream the music in this service obtained from:
ONE LICENSE, License: A-711192
CCLI License: 3175826
CCS License: 11563
All rights reserved.
```

`snippets/minnehaha-footer.txt.j2` is the three parts separated by one blank line. Its output is byte-identical to 003's footer, so 003 SC-001a is unaffected:
```jinja
{% include "snippets/bulletin.txt.j2" %}

{% include "snippets/links.txt.j2" %}

{% include "snippets/licensing.txt.j2" %}
```

## Taizé

`taize-title.txt.j2`: `{{ date_long }} - Taizé`

`taize-description.txt.j2`:
```jinja
Welcome to {{ church_name }} on {{ date_long }} for Taizé prayer!

{% include "snippets/minnehaha-footer.txt.j2" %}
```

| Event | Title | Line 1 |
|---|---|---|
| Fri 2026-10-09 19:00 "Taizé" | `October 9th, 2026 - Taizé` | `Welcome to Minnehaha United Methodist Church on October 9th, 2026 for Taizé prayer!` |
| Fri 2026-11-13 19:00 "Taize Prayer" | `November 13th, 2026 - Taizé` | `… on November 13th, 2026 for Taizé prayer!` |

## Funeral

| File | Content |
|---|---|
| `funeral-title.txt.j2` | `{{ date_long }} - {{ funeral.wording }} for {{ funeral.name }}` |
| `funeral-title-short.txt.j2` | `{{ date_long }} - {{ "Memorial" if "memorial" in funeral.wording\|lower else "Funeral" }} for {{ funeral.name }}` |
| `funeral-title-shortest.txt.j2` | `{{ date_short }} - {{ "Memorial" if "memorial" in funeral.wording\|lower else "Funeral" }} for {{ funeral.name }}` |

`funeral-description.txt.j2`:
```jinja
Welcome to {{ church_name }} on {{ date_long }} for the {{ funeral.wording|lower }} of {{ funeral.name }}.
{% if funeral.years %}
In loving memory of {{ funeral.name }} ({{ funeral.years }}).
{% endif %}
{% if funeral.obituary %}
Obituary: {{ funeral.obituary }}
{% endif %}
{% if funeral.memorials %}
Memorials: {{ funeral.memorials }}
{% endif %}

{% include "snippets/links.txt.j2" %}

{% include "snippets/licensing.txt.j2" %}
```

### Expected renders

| Event | Title | Description (before the links block) |
|---|---|---|
| Fri 2026-10-23 11:00, title "Funeral for Jane Doe" | `October 23rd, 2026 - Funeral for Jane Doe` | `Welcome to Minnehaha United Methodist Church on October 23rd, 2026 for the funeral of Jane Doe.` |
| Same, plus `yt.wording: Celebration of Life`, `yt.years: 1941–2026`, `yt.obituary: https://example.org/obit/jane-doe` | `October 23rd, 2026 - Celebration of Life for Jane Doe` | Line 1 `… for the celebration of life of Jane Doe.`, then `In loving memory of Jane Doe (1941–2026).`, then `Obituary: https://example.org/obit/jane-doe` |
| A 70-character name with `Celebration of Life` | Candidate 1 is too long, so candidate 2 is used: `October 23rd, 2026 - Funeral for <name>` | Unchanged. The full name is kept in the description. |
| Title "Funeral" with no `yt.name` | (not published) | Occurrence `failed`: `Funeral needs a name: …` |

Each funeral description has no bulletin line and no "Peace and good health" line, which belong to the Sunday bulletin. The links and licensing blocks are identical to the Sunday footer.
