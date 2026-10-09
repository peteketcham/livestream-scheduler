# Contract: Liturgical Calendar (computed names, year, season)

The module is `liturgy.calendar` and is pure. The function is `liturgical_day(date, local_time | None) → LiturgicalDay | None`. It returns `None` for dates with no named observance, for example an ordinary Tuesday.

`LiturgicalDay` = `{ day_name, year ("A"|"B"|"C"), season, default_color, is_sunday }`.

## Anchors

| Anchor | Rule |
|---|---|
| Easter (E) | Gregorian computus (anonymous algorithm) |
| Advent 1 (A) | The fourth Sunday before Dec 25 (Nov 27 – Dec 3) |
| Ash Wednesday | E − 46 days |
| Day of Pentecost (P) | E + 49 days |
| Lectionary year | Liturgical year beginning on Advent 1 of calendar year Y: `"ABC"[Y % 3]`. Advent 2025 is A, Advent 2026 is B, Advent 2027 is C. |

## Names

The canonical forms follow the site's **current** (2025–2026) usage. Ordinals are spelled out as First … Twenty-Eighth, hyphenated from Twenty-First on.

| Date | Name | Season / default color |
|---|---|---|
| Sundays A, A+7, A+14, A+21 | `First … Fourth Sunday of Advent` | Advent / Purple |
| Dec 24 (any weekday). If Dec 24 is a Sunday: services starting before 16:00 local are `Fourth Sunday of Advent`. | `Christmas Eve` | Christmas / White |
| Dec 25 | `Christmas Day` | Christmas / White |
| Sundays Dec 26 – Jan 1 | `First Sunday after Christmas` | Christmas / White |
| Sunday Jan 2 – Jan 6 | `Epiphany of the Lord` | Epiphany / White |
| Sunday Jan 7 – Jan 13 | `Baptism of the Lord` | Season after Epiphany / White |
| Following Sundays until Transfiguration | `Second … Ninth Sunday after the Epiphany`, counted with Baptism as First | Season after Epiphany / Green |
| Sunday before Ash Wednesday | `Transfiguration Sunday` | Season after Epiphany / White |
| E − 46 (Wed) | `Ash Wednesday` | Lent / Purple |
| Sundays in Lent | `First … Fifth Sunday in Lent` | Lent / Purple |
| E − 7 | `Palm / Passion Sunday` | Holy Week / Purple |
| E − 3, E − 2, E − 1 | `Maundy Thursday`, `Good Friday`, `Holy Saturday` | Holy Week / Purple, Black, Black |
| E | `Easter Sunday` | Easter / White |
| E + 7 … E + 42 | `Second … Seventh Sunday of Easter` | Easter / White |
| E + 39 (Thu) | `Ascension of the Lord` | Easter / White |
| P | `Day of Pentecost` | Pentecost / Red |
| P + 7 | `Trinity Sunday` | Season after Pentecost / White |
| P + 14 … A − 7 | `Second … Twenty-Eighth Sunday after Pentecost` (n = weeks since P; Trinity Sunday is the First) | Season after Pentecost / Green |
| Jan 1 when not a Sunday | `New Year's Day` | Christmas / White |

Any other weekday returns `None`. The site's occasional named services (Watch Night, Las Posadas, Blue Christmas) are not computed. The owner can supply them with `yt.day-name`.

## Church naming preferences (aliases)

`lectionary.name_aliases` (config) maps a computed name to the church's preferred name. It is applied after computation and before templating. Defaults, from the channel history ([reference](../reference/sunday-examples.md#channel-history-titles-captured-2026-10-08-from-the-channels-live-tab)):

| Computed | Church uses |
|---|---|
| `Day of Pentecost` | `Pentecost` |
| `Trinity Sunday` | `First Sunday after Pentecost` |

## Special days (owner list; separate from the name)

Configured in `lectionary.special_days` ([config-additions.md](config-additions.md)). Each matching rule adds a name to `special_names`. Supported rules:

| Rule | Example |
|---|---|
| `first_sunday_of: <month>` | All Saints Sunday → `november` |
| `nth_sunday: {month, n}` | World Communion Sunday → `{month: october, n: 1}` |
| `sunday_before: advent` | Reign of Christ / Christ the King Sunday |
| `fixed: MM-DD` | |
| `easter_offset: <days>` | |
| `pentecost_offset: <days>` | |

**Default list**:
- `All Saints Sunday` (`first_sunday_of: november`)
- `Reign of Christ / Christ the King Sunday` (`sunday_before: advent`)

## Verification (worked examples, also unit tests)

| Date | Expected |
|---|---|
| 2026-09-27 | Eighteenth Sunday after Pentecost, A |
| 2026-10-04 | Nineteenth Sunday after Pentecost, A (no special name by default) |
| 2026-10-18 | Twenty-First Sunday after Pentecost, A |
| 2026-11-01 | Twenty-Third Sunday after Pentecost, A + special `All Saints Sunday` |
| 2026-11-22 | Twenty-Sixth Sunday after Pentecost, A + special `Reign of Christ / Christ the King Sunday` |
| 2026-11-29 | First Sunday of Advent, B |
| 2026-12-24 | Christmas Eve, B |
| 2026-04-05 | Easter Sunday, A |
| 2026-05-24 | Day of Pentecost → alias **Pentecost**, A |
| 2026-05-31 | Trinity Sunday → alias **First Sunday after Pentecost**, A |
| 2023-12-24 09:30 / 18:00 | Fourth Sunday of Advent / Christmas Eve, B |

**Oracle**: a prototype run against the site's 2019–2026 export matched 376 of 412 entries after alias normalization. The 36 others were all special-name substitutions, wording variants ("Pentecost Sunday", "Easter Sunday 2024"), or named services not computed (Watch Night, Las Posadas). One rule error was found and corrected (the Epiphany vs. Baptism window). The test suite keeps the export as a fixture together with an explicit divergence table, and fails on any new divergence.
