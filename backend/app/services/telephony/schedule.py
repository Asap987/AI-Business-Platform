"""Opening hours for a department. Pure functions (no database) so every rule is easy to test.

Format: ``None`` means always open. Otherwise a mapping of day keys ``mon``..``sun`` to a list of ``["HH:MM", "HH:MM"]``
intervals in the department's time zone. A day that is missing is closed all day; ``{}`` means closed every day.
An interval is open from its start up to, not including, its end.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
_TIME = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def _minutes(text: str) -> int:
    return int(text[:2]) * 60 + int(text[3:])


def validate_hours(hours: object) -> str | None:
    """Return a plain-language problem, or None when the hours are acceptable."""
    if hours is None:
        return None
    if not isinstance(hours, dict):
        return "Opening hours must be a list of days with times."
    for day, spans in hours.items():
        if day not in DAYS:
            return f"Unknown day “{str(day)[:10]}”. Use mon, tue, wed, thu, fri, sat, sun."
        if not isinstance(spans, list) or len(spans) > 4:
            return f"{day}: give between 0 and 4 time ranges."
        last_end = -1
        for span in sorted((s for s in spans if isinstance(s, list)), key=lambda s: str(s[0]) if s else ""):
            if len(span) != 2 or not all(isinstance(t, str) and _TIME.match(t) for t in span):
                return f"{day}: times must look like 08:00."
            start, end = _minutes(span[0]), _minutes(span[1])
            if start >= end:
                return f"{day}: a range must end after it starts."
            if start < last_end:
                return f"{day}: time ranges must not overlap."
            last_end = end
        if any(not isinstance(s, list) for s in spans):
            return f"{day}: times must look like 08:00."
    return None


def valid_timezone(name: str | None) -> bool:
    if name is None:
        return True
    try:
        ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError, OSError):
        return False
    return True


def is_open(hours: object, tz_name: str | None, now: datetime | None = None) -> bool:
    """Is a department open at ``now``? Missing or unreadable hours mean always open only when ``hours`` is None."""
    if hours is None:
        return True
    if validate_hours(hours) is not None:
        return False  # unreadable stored hours: do not promise anyone is there
    try:
        zone = ZoneInfo(tz_name or "UTC")
    except (ZoneInfoNotFoundError, ValueError, OSError):
        zone = timezone.utc
    local = (now or datetime.now(timezone.utc)).astimezone(zone)
    minute = local.hour * 60 + local.minute
    return any(_minutes(a) <= minute < _minutes(b) for a, b in hours.get(DAYS[local.weekday()], []))
