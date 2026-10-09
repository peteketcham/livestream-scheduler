# Reference: Existing Minnehaha UMC Sunday Livestreams

Captured 2026-10-08 from the public watch pages. Channel: **Minnehaha UMC**, `UCzwZQ34D3RZEncTf6fAe0hQ`, @minnehahaumc.

These are the format that templated Sunday livestreams must reproduce. See spec FR-005 and US1.

## Example 1: https://youtube.com/live/yk_L_oyXS8A

- **Title**: `October 4th, 2026 - Nineteenth Sunday after Pentecost`
- **Went live**: 2026-10-04 14:31 UTC (09:31 America/Chicago). **Ended**: 15:39 UTC. Length 1 h 08 m.
- **Description** (verbatim):

```text
Welcome to Minnehaha United Methodist Church on October 4th, 2026 for the nineteenth Sunday after Pentecost!

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

## Example 2: https://youtube.com/live/4ZeLbRb6Qiw

- **Title**: `September 27th, 2026 - Eighteenth Sunday after Pentecost`
- **Went live**: 2026-09-27 14:25 UTC (09:25 America/Chicago). **Ended**: 15:27 UTC. Length 1 h 01 m.
- **Description**: identical to Example 1 except the first line, `Welcome to Minnehaha United Methodist Church on September 27th, 2026 for the Eighteenth Sunday after Pentecost!`

## Derived pattern

| Part | Pattern | Varies per week? |
|---|---|---|
| Title | `<Month> <day with ordinal suffix>, <year> - <liturgical day name>` | Yes: date and liturgical day |
| Description line 1 | `Welcome to Minnehaha United Methodist Church on <same date> for the <liturgical day name>!` | Yes: date and liturgical day |
| Bulletin line | Fixed URL `https://minnehaha.org/documents/Bulletin.pdf`. The same file is overwritten each week. | No |
| Links block | Website, Facebook, Instagram | No |
| Music licensing block | ONE LICENSE A-711192, CCLI 3175826, CCS 11563, "All rights reserved." | No |

Observations:
- The liturgical day name appears **without** the lectionary year (", Year A") and without series prefixes ("Week 4 – …"), although the lectionary site includes both.
- The capitalization of the liturgical day inside the welcome line was inconsistent across weeks ("nineteenth" vs "Eighteenth"). This is a manual-typing artifact the template removes. The template will use the site's capitalization ("Nineteenth Sunday after Pentecost").
- Neither description lists scripture readings, the liturgical color, or the sermon/series title. Those are available but not part of the current format.
- The streams start around 9:30 AM Central and run about 60–70 minutes.
- The video category is "Entertainment". That is set on the video, not the scheduled event, and is out of scope.

## Channel history (titles, captured 2026-10-08 from the channel's Live tab)

| Date | Title | Notes |
|---|---|---|
| 2026-10-09 (Fri, upcoming, 7:00 PM CDT) | `October 9th, 2026 - Taizé` | Created by hand. Its description is a **copy of the Oct 4 Sunday description** (wrong date and day), the error templates prevent. |
| 2026-06-07 … 2026-10-04 | `<date> - <Nth> Sunday after Pentecost` | Pattern as above |
| 2026-05-31 | `May 31st, 2026 - First Sunday after Pentecost` | Church says **"First Sunday after Pentecost"**, not "Trinity Sunday". Welcome line: "…for the first Sunday after Pentecost!" |
| 2026-05-24 | `May 24th, 2026 - Pentecost` | Church says **"Pentecost"**, not "Day of Pentecost". Welcome line: "…for Pentecost!" (no article) |
| 2026-05-17 | `May 17th, 2026 - Seventh Sunday of Easter and the Stone Soup Musical` | Title **extra** appended |
| 2026-04-12 … 2026-05-10 | `<date> - <Nth> Sunday of Easter` | |
| 2026-04-10 (Fri, ~6:55 PM CDT, 65 min) | `April 10th Taize` | Ad hoc format. Description: "Welcome to Minnehaha United Methodist Church on April 10th 2026 Taize!" plus the standard footer |
| 2026-04-05 (11:00 AM) | `April 5th, 2026 - Easter Sunday with the band` | Title extra. Welcome line: "…for Easter Sunday!" (no article) |
| 2026-04-?? | `Eagle Court of Honor - Cullan F` | Not a worship service, and it names a person |

Service start times observed: 9:30 AM (September–October), 10:00 AM (May–June), 11:00 AM (Easter). All come from the calendar event, not from configuration.
