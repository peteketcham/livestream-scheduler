"""Expand an ICS feed into instances within a window (research R2, contracts/calendar-mapping.md).

Identity: non-recurring events are keyed by UID; instances of recurring series by
UID + "|" + their *original* start in UTC (RECURRENCE-ID), so moving one instance is an update.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import icalendar
import recurring_ical_events

from ..timeutil import to_iso


class FeedError(Exception):
    """The calendar feed could not be fetched or parsed (exit code 4; never causes removals)."""


@dataclass(frozen=True)
class Instance:
    uid: str
    key: str
    recurring: bool
    original_start_utc: datetime | None
    start: datetime  # aware, in the event's own zone
    end: datetime | None  # None when the event has neither DTEND nor DURATION
    tz: str
    summary: str
    description: str
    all_day: bool = False


@dataclass
class ExpandResult:
    instances: list[Instance] = field(default_factory=list)
    all_day: list[Instance] = field(default_factory=list)
    event_count: int = 0


def parse(data: bytes) -> icalendar.Calendar:
    try:
        cal = icalendar.Calendar.from_ical(data)
    except Exception as e:  # icalendar raises ValueError and friends
        raise FeedError(f"calendar feed is not valid iCalendar: {e}") from None
    if cal.name != "VCALENDAR":
        raise FeedError("calendar feed is not a VCALENDAR")
    return cal


def _tz_name(dt: datetime, default_tz: str) -> str:
    tz = dt.tzinfo
    if tz is None:
        return default_tz
    key = getattr(tz, "key", None) or getattr(tz, "zone", None)
    if key:
        return str(key)
    return "UTC" if dt.utcoffset() == timedelta(0) else default_tz


def _localize(value: Any, default: ZoneInfo) -> Any:
    if isinstance(value, datetime) and value.tzinfo is None:
        return value.replace(tzinfo=default)
    return value


def expand(
    data: bytes, window_start: datetime, window_end: datetime, default_tz: str
) -> ExpandResult:
    cal = parse(data)
    default = ZoneInfo(default_tz)
    events = [c for c in cal.walk("VEVENT")]
    recurring_uids = {
        str(c.get("UID"))
        for c in events
        if c.get("RRULE") is not None
        or c.get("RDATE") is not None
        or c.get("RECURRENCE-ID") is not None
    }
    explicit_end = {
        (str(c.get("UID")), _rid_key(c, default))
        for c in events
        if c.get("DTEND") is not None or c.get("DURATION") is not None
    }
    explicit_end_uids = {
        str(c.get("UID"))
        for c in events
        if c.get("RECURRENCE-ID") is None
        and (c.get("DTEND") is not None or c.get("DURATION") is not None)
    }

    result = ExpandResult(event_count=len({str(c.get("UID")) for c in events}))
    try:
        occurrences = recurring_ical_events.of(cal).between(window_start, window_end)
    except Exception as e:
        raise FeedError(f"calendar feed could not be expanded: {e}") from None

    for ev in occurrences:
        if str(ev.get("STATUS", "")).upper() == "CANCELLED":
            continue
        uid = str(ev.get("UID"))
        start_raw = ev.get("DTSTART").dt
        summary = str(ev.get("SUMMARY", "") or "")
        description = str(ev.get("DESCRIPTION", "") or "")
        recurring = uid in recurring_uids
        if isinstance(start_raw, date) and not isinstance(start_raw, datetime):
            day = datetime(start_raw.year, start_raw.month, start_raw.day, tzinfo=default)
            result.all_day.append(
                Instance(
                    uid, uid, recurring, None, day, None, default_tz, summary, description, True
                )
            )
            continue

        tz = _tz_name(start_raw, default_tz)
        start = _localize(start_raw, default)
        if start < window_start:
            continue
        rid = ev.get("RECURRENCE-ID")
        original = _localize(rid.dt, default) if rid is not None else start
        original_utc = original.astimezone(UTC) if recurring else None
        key = f"{uid}|{to_iso(original_utc)}" if original_utc is not None else uid

        end: datetime | None = None
        has_end = (uid, to_iso(original.astimezone(UTC))) in explicit_end or (
            uid in explicit_end_uids
        )
        if has_end and ev.get("DTEND") is not None:
            end = _localize(ev.get("DTEND").dt, default)
            if end is not None and end <= start:
                end = None
        result.instances.append(
            Instance(
                uid=uid,
                key=key,
                recurring=recurring,
                original_start_utc=original_utc,
                start=start,
                end=end,
                tz=tz,
                summary=summary,
                description=description,
            )
        )
    result.instances.sort(key=lambda i: (i.start.astimezone(UTC), i.key))
    return result


def _rid_key(component: Any, default: ZoneInfo) -> str | None:
    rid = component.get("RECURRENCE-ID")
    if rid is None:
        return None
    value = _localize(rid.dt, default)
    return to_iso(value.astimezone(UTC)) if isinstance(value, datetime) else None
