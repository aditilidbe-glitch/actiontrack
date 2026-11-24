"""Due-date resolution (spec R-DAT-01, R-DAT-02, R-DAT-03).

Pure functions only: nothing here reads the clock. "Today" is always passed in.
"""

from __future__ import annotations

import calendar
import re
from dataclasses import dataclass
from datetime import date, timedelta

STATUS_OPEN = "open"
STATUS_DONE = "done"
STATUS_OVERDUE = "overdue"

DAYS_IN_WEEK = 7
FRIDAY_INDEX = 4

_WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
_MONTHS = [
    "january", "february", "march", "april", "may", "june",
    "july", "august", "september", "october", "november", "december",
]

_WEEKDAY_RE = (
    r"(?:mon(?:day)?|tue(?:s(?:day)?)?|wed(?:nesday)?|thu(?:r(?:s(?:day)?)?)?|"
    r"fri(?:day)?|sat(?:urday)?|sun(?:day)?)"
)
_MONTH_RE = (
    r"(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|june?|july?|aug(?:ust)?|"
    r"sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?)"
)
_DAY_RE = r"\d{1,2}(?:st|nd|rd|th)?"

_ISO_RE = r"\d{4}-\d{2}-\d{2}"
_DAY_MONTH_RE = rf"(?:{_WEEKDAY_RE}\.?,?\s+)?{_DAY_RE}\s+{_MONTH_RE}(?:,?\s+\d{{4}})?"
_MONTH_DAY_RE = rf"(?:{_WEEKDAY_RE}\.?,?\s+)?{_MONTH_RE}\s+{_DAY_RE}(?:,?\s+\d{{4}})?"
_RELATIVE_RE = (
    r"(?:eod\s+tomorrow|eod|tomorrow|end\s+of\s+(?:next\s+)?week|end\s+of\s+(?:the\s+)?month|"
    rf"next\s+{_WEEKDAY_RE}|mid[-\s]?{_MONTH_RE})"
)
_PHRASE_RE = (
    rf"(?:{_ISO_RE}|{_DAY_MONTH_RE}|{_MONTH_DAY_RE}|{_RELATIVE_RE}|{_WEEKDAY_RE})"
)
_DUE_SEARCH = re.compile(
    rf"\b(?:by|due|from|on|before)\s+({_PHRASE_RE})(?![\w%])",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class DuePhrase:
    """A due-date phrase found inside item text, with its position."""

    text: str
    start: int
    end: int


@dataclass(frozen=True)
class DueResult:
    """Outcome of resolving a due phrase (R-DAT-01/02)."""

    iso: str | None
    raw: str | None
    vague: bool
    warning: str | None = None


def extract_due_phrase(text: str) -> DuePhrase | None:
    """Find the last due-date phrase in item text, or None."""
    last: DuePhrase | None = None
    for match in _DUE_SEARCH.finditer(text):
        last = DuePhrase(match.group(1), match.start(1), match.end(1))
    return last


MIN_ABBREVIATION_LENGTH = 3


def _prefix_index(token: str, names: list[str], start: int) -> int | None:
    """Index of the name that `token` abbreviates ('wed', 'sept'), or None."""
    lowered = token.lower().strip(".,")
    if lowered == "sept":
        lowered = "sep"
    if len(lowered) < MIN_ABBREVIATION_LENGTH:
        return None
    for index, name in enumerate(names, start=start):
        if name.startswith(lowered):
            return index
    return None


def _weekday_index(token: str) -> int | None:
    return _prefix_index(token, _WEEKDAYS, 0)


def _month_index(token: str) -> int | None:
    return _prefix_index(token, _MONTHS, 1)


def _monday_of_week(day: date) -> date:
    return day - timedelta(days=day.weekday())


def _next_weekday_after(meeting: date, weekday: int) -> date:
    delta = (weekday - meeting.weekday()) % DAYS_IN_WEEK
    return meeting + timedelta(days=delta or DAYS_IN_WEEK)


def _calendar_date(day: int, month: int, year: int | None, meeting: date | None) -> date:
    """Build a date; with no explicit year use the meeting year, rolling forward."""
    if year is not None:
        return date(year, month, day)
    if meeting is None:
        raise ValueError("a meeting date is required when the year is omitted")
    candidate = date(meeting.year, month, day)
    if candidate < meeting:
        candidate = date(meeting.year + 1, month, day)
    return candidate


_DAY_MONTH_PARTS = re.compile(
    rf"(?:(?P<wd>{_WEEKDAY_RE})\.?,?\s+)?(?P<day>\d{{1,2}})(?:st|nd|rd|th)?\s+"
    rf"(?P<month>{_MONTH_RE})(?:,?\s+(?P<year>\d{{4}}))?$",
    re.IGNORECASE,
)
_MONTH_DAY_PARTS = re.compile(
    rf"(?:(?P<wd>{_WEEKDAY_RE})\.?,?\s+)?(?P<month>{_MONTH_RE})\s+"
    rf"(?P<day>\d{{1,2}})(?:st|nd|rd|th)?(?:,?\s+(?P<year>\d{{4}}))?$",
    re.IGNORECASE,
)


def _parse_calendar(phrase: str, meeting: date | None) -> tuple[date, str | None] | None:
    """Parse explicit calendar dates. Returns (date, warning) or None."""
    if re.fullmatch(_ISO_RE, phrase):
        return date.fromisoformat(phrase), None
    for pattern in (_DAY_MONTH_PARTS, _MONTH_DAY_PARTS):
        match = pattern.match(phrase)
        if not match:
            continue
        month = _month_index(match.group("month"))
        year = int(match.group("year")) if match.group("year") else None
        if month is None:
            return None
        result = _calendar_date(int(match.group("day")), month, year, meeting)
        return result, _weekday_warning(match.group("wd"), result)
    return None


def _weekday_warning(weekday_token: str | None, resolved: date) -> str | None:
    if not weekday_token:
        return None
    expected = _weekday_index(weekday_token)
    if expected is not None and expected != resolved.weekday():
        return f"weekday '{weekday_token}' does not match {resolved.isoformat()}"
    return None


def _resolve_relative(phrase: str, meeting: date) -> date | None:
    lowered = re.sub(r"\s+", " ", phrase.lower().strip())
    simple = {
        "tomorrow": meeting + timedelta(days=1),
        "eod tomorrow": meeting + timedelta(days=1),
        "eod": meeting,
        "end of next week": _monday_of_week(meeting) + timedelta(days=DAYS_IN_WEEK + FRIDAY_INDEX),
        "end of week": _monday_of_week(meeting) + timedelta(days=FRIDAY_INDEX),
    }
    if lowered in simple:
        return simple[lowered]
    if lowered in ("end of month", "end of the month"):
        return meeting.replace(day=calendar.monthrange(meeting.year, meeting.month)[1])
    if lowered.startswith("next "):
        index = _weekday_index(lowered[5:])
        if index is not None:
            return _monday_of_week(meeting) + timedelta(days=DAYS_IN_WEEK + index)
    return None


def _resolve_phrase(phrase: str, meeting: date) -> tuple[date | None, str | None]:
    """Resolve a cleaned phrase to a date, or (None, None) when it is vague."""
    cleaned = re.sub(r"^(?:by|due|from|on|before)\s+", "", phrase.strip(), flags=re.IGNORECASE)
    try:
        calendar_hit = _parse_calendar(cleaned, meeting)
        if calendar_hit:
            return calendar_hit
        relative = _resolve_relative(cleaned, meeting)
        if relative:
            return relative, None
        if re.fullmatch(_WEEKDAY_RE, cleaned, re.IGNORECASE):
            index = _weekday_index(cleaned)
            return (_next_weekday_after(meeting, index), None) if index is not None else (None, None)
    except ValueError:
        return None, None
    return None, None


def resolve_due(phrase: str | None, meeting: date) -> DueResult:
    """Resolve a due phrase relative to the meeting date (R-DAT-01/02)."""
    if phrase is None or not phrase.strip():
        return DueResult(iso=None, raw=None, vague=False)
    raw = phrase.strip()
    resolved, warning = _resolve_phrase(raw, meeting)
    if resolved is None:
        return DueResult(iso=None, raw=raw, vague=True)
    return DueResult(iso=resolved.isoformat(), raw=raw, vague=False, warning=warning)


def parse_header_date(text: str) -> date | None:
    """Parse an absolute meeting date from a note header; None if unparseable."""
    cleaned = text.strip()
    if not cleaned:
        return None
    try:
        if re.fullmatch(_ISO_RE, cleaned):
            return date.fromisoformat(cleaned)
        for pattern in (_DAY_MONTH_PARTS, _MONTH_DAY_PARTS):
            match = pattern.match(cleaned)
            if match and match.group("year"):
                month = _month_index(match.group("month"))
                if month is not None:
                    return date(int(match.group("year")), month, int(match.group("day")))
    except ValueError:
        return None
    return None


def compute_status(done: bool, due_iso: str | None, today: date) -> str:
    """done / overdue / open (R-DAT-03). Items with no due date are never overdue."""
    if done:
        return STATUS_DONE
    if due_iso is not None and date.fromisoformat(due_iso) < today:
        return STATUS_OVERDUE
    return STATUS_OPEN
