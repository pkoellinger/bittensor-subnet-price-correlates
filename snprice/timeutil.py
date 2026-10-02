"""UTC timestamps as text and as seconds since 1970, independent of the computer's time zone."""
import calendar
import re
import time

_UTC_TEXT = re.compile(r"^(\d{4}-\d{2}-\d{2})[T ](\d{2}:\d{2}:\d{2})(?:\.\d+)?(?:Z|\+00:00)?$")


def epoch(text):
    """Seconds since 1970 of a UTC timestamp such as "2026-09-15T12:00:00Z" or "2026-09-15 12:00:00"."""
    m = _UTC_TEXT.match(str(text).strip())
    if not m:
        raise ValueError(f"not a UTC timestamp: {text!r}")
    return calendar.timegm(time.strptime(m.group(1) + " " + m.group(2), "%Y-%m-%d %H:%M:%S"))


def iso(seconds):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(seconds))
