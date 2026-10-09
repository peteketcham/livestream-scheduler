"""Calendar instance → desired livestream occurrence (contracts/calendar-mapping.md)."""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from html.parser import HTMLParser
from typing import ClassVar

from ..config import Config
from ..timeutil import to_iso
from ..youtube.port import BroadcastSpec, managed_hash
from .expand import Instance

TITLE_MAX = 100
DESCRIPTION_MAX_BYTES = 5000

# Directives understood by 001; later features register more (002–004).
KNOWN_DIRECTIVES: set[str] = {"visibility", "stream", "allow-overlap"}

_DIRECTIVE = re.compile(r"^\s*yt\.([a-z0-9][a-z0-9.\-]*)\s*:\s*(.*?)\s*$", re.I)
_TAG = re.compile(r"<\s*/?\s*[a-zA-Z][^>]*>")


@dataclass
class DesiredOccurrence:
    key: str
    ical_uid: str
    original_start_utc: datetime | None
    title: str
    description: str
    start_utc: datetime
    end_utc: datetime
    source_tz: str
    visibility: str
    directives: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    allow_overlap: bool = False
    error: str | None = None
    made_for_kids: bool = False
    auto_start: bool = False
    auto_stop: bool = False
    dvr: bool = True

    def spec(self) -> BroadcastSpec:
        return BroadcastSpec(
            title=self.title,
            description=self.description,
            start_utc=self.start_utc,
            end_utc=self.end_utc,
            privacy=self.visibility,
            made_for_kids=self.made_for_kids,
            auto_start=self.auto_start,
            auto_stop=self.auto_stop,
            dvr=self.dvr,
        )

    @property
    def desired_hash(self) -> str:
        return managed_hash(
            self.title, self.description, self.start_utc, self.end_utc, self.visibility
        )

    @property
    def original_start_iso(self) -> str | None:
        return to_iso(self.original_start_utc) if self.original_start_utc else None


@dataclass
class MappingResult:
    desired: list[DesiredOccurrence] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class _HTMLToText(HTMLParser):
    BLOCK_END: ClassVar[set[str]] = {"p", "div", "li", "tr", "h1", "h2", "h3", "h4", "h5", "h6"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._href: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "br":
            self.parts.append("\n")
        elif tag == "a":
            self._href = dict(attrs).get("href")

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._href:
            self.parts.append(f": {self._href}")
            self._href = None
        elif tag in self.BLOCK_END:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def html_to_text(text: str) -> str:
    """Google Calendar exports HTML descriptions; turn them into plain text."""
    if not _TAG.search(text):
        return text
    parser = _HTMLToText()
    parser.feed(text)
    parser.close()
    out = "".join(parser.parts)
    out = html.unescape(out)
    return out.replace("\xa0", " ")


def split_directives(text: str) -> tuple[str, dict[str, str]]:
    """Remove `yt.<name>: <value>` lines; return (remaining text, directives)."""
    directives: dict[str, str] = {}
    kept: list[str] = []
    for line in text.split("\n"):
        m = _DIRECTIVE.match(line)
        if m:
            directives[m.group(1).lower()] = m.group(2)
        else:
            kept.append(line)
    return "\n".join(kept), directives


def clean_description(text: str, warnings: list[str]) -> str:
    if "<" in text or ">" in text:
        text = text.replace("<", "").replace(">", "")
        warnings.append("removed < or > from description (not allowed by YouTube)")
    text = text.strip("\n")
    lines = [ln.rstrip("\r") for ln in text.split("\n")]
    text = "\n".join(lines).strip("\n")
    encoded = text.encode("utf-8")
    if len(encoded) > DESCRIPTION_MAX_BYTES:
        text = encoded[:DESCRIPTION_MAX_BYTES].decode("utf-8", errors="ignore")
        warnings.append(f"description truncated to {DESCRIPTION_MAX_BYTES} bytes")
    return text


def clean_title(text: str, warnings: list[str]) -> str:
    text = " ".join(text.replace("<", "").replace(">", "").split())
    if len(text) > TITLE_MAX:
        text = text[:TITLE_MAX]
        warnings.append(f"title truncated to {TITLE_MAX} characters")
    return text


def _truthy(value: str | None) -> bool:
    return (value or "").strip().lower() in {"yes", "true", "1", "y"}


def map_instance(inst: Instance, cfg: Config) -> DesiredOccurrence | None:
    """Map one instance; None means excluded by the `calendar.include` filter."""
    warnings: list[str] = []
    text = html_to_text(inst.description.replace("\r\n", "\n"))
    text, directives = split_directives(text)

    title_raw = inst.summary
    include = cfg.calendar.include
    if include.summary_prefix is not None:
        if not title_raw.startswith(include.summary_prefix):
            return None
        title_raw = title_raw[len(include.summary_prefix) :]
    if include.directive and not _truthy(directives.get("stream")):
        return None

    for name in directives:
        if name not in KNOWN_DIRECTIVES:
            warnings.append(f"unknown directive yt.{name} (ignored)")

    visibility = cfg.defaults.visibility
    if "visibility" in directives:
        v = directives["visibility"].strip().lower()
        if v in ("public", "unlisted", "private"):
            visibility = v  # type: ignore[assignment]
        else:
            warnings.append(f"invalid yt.visibility {v!r}; using {visibility}")

    start_utc = inst.start.astimezone(UTC)
    end = inst.end.astimezone(UTC) if inst.end is not None else start_utc + timedelta(hours=1)
    title = clean_title(title_raw, warnings)
    description = clean_description(text, warnings)
    d = DesiredOccurrence(
        key=inst.key,
        ical_uid=inst.uid,
        original_start_utc=inst.original_start_utc,
        title=title,
        description=description,
        start_utc=start_utc,
        end_utc=end,
        source_tz=inst.tz,
        visibility=visibility,
        directives=directives,
        warnings=warnings,
        allow_overlap=_truthy(directives.get("allow-overlap")),
        made_for_kids=cfg.defaults.made_for_kids,
        auto_start=cfg.defaults.enable_auto_start,
        auto_stop=cfg.defaults.enable_auto_stop,
        dvr=cfg.defaults.enable_dvr,
    )
    if not title:
        d.error = "Event has no title"
    duration = end - start_utc
    if duration < timedelta(minutes=1) or duration > timedelta(hours=12):
        d.error = "Event must last between 1 minute and 12 hours"
    return d


def map_instances(instances: list[Instance], cfg: Config) -> MappingResult:
    res = MappingResult()
    for inst in instances:
        d = map_instance(inst, cfg)
        if d is not None:
            res.desired.append(d)
    return res


def all_day_warning(inst: Instance) -> str:
    when: datetime = inst.start
    return f'all-day event "{inst.summary}" on {when.date()} skipped (no start time)'
