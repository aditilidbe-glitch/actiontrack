"""Note reading and header parsing (spec R-ING-03, R-ING-04, R-SAF-02).

Files are opened read-only. Nothing here raises for a bad note: bad notes come
back as `SkippedNote` with a reason so ingest can report them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from actiontrack.dates import parse_header_date

REASON_EMPTY = "empty file"
REASON_NOT_UTF8 = "not valid UTF-8 text"
REASON_NO_HEADER = "no meeting header or date"
REASON_NO_TITLE = "no meeting title"
REASON_NO_DATE = "no resolvable meeting date"
REASON_NOT_MARKDOWN = "not a markdown note"
WARNING_DATE_FROM_FILENAME = "meeting date taken from filename"

MARKDOWN_SUFFIX = ".md"
_FRONT_MATTER_FENCE = "---"
_MEETING_TITLE_RE = re.compile(r"^#\s+Meeting:\s*(?P<title>.+?)\s*$", re.IGNORECASE)
_DATE_RE = re.compile(r"^Date:\s*(?P<value>.*?)\s*$", re.IGNORECASE)
_ATTENDEES_RE = re.compile(r"^Attendees:\s*(?P<value>.*?)\s*$", re.IGNORECASE)
_FILENAME_DATE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})")


@dataclass(frozen=True)
class Note:
    """A successfully read meeting note."""

    path: Path
    file: str
    title: str
    meeting_date: date
    attendees: tuple[str, ...]
    lines: tuple[str, ...]
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True)
class SkippedNote:
    """A file that was not ingested, with the reason (R-ING-03)."""

    file: str
    reason: str


def discover(folder: Path, recursive: bool = False) -> tuple[list[Path], list[SkippedNote]]:
    """List markdown files in `folder`; other files are reported as skipped."""
    pattern = "**/*" if recursive else "*"
    candidates = sorted(p for p in folder.glob(pattern) if p.is_file())
    notes = [p for p in candidates if p.suffix.lower() == MARKDOWN_SUFFIX]
    skipped = [
        SkippedNote(_display_name(p, folder), REASON_NOT_MARKDOWN)
        for p in candidates
        if p.suffix.lower() != MARKDOWN_SUFFIX
    ]
    return notes, skipped


def _display_name(path: Path, folder: Path) -> str:
    try:
        return path.relative_to(folder).as_posix()
    except ValueError:
        return path.name


def _decode(raw: bytes) -> str | None:
    if b"\x00" in raw:
        return None
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return None


def _split_attendees(value: str) -> tuple[str, ...]:
    cleaned = value.strip().strip("[]")
    return tuple(part.strip().strip("'\"") for part in cleaned.split(",") if part.strip())


def _parse_front_matter(lines: list[str]) -> dict[str, str] | None:
    """Return key/value pairs of a leading `---` block, or None if absent."""
    if not lines or lines[0].strip() != _FRONT_MATTER_FENCE:
        return None
    fields: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == _FRONT_MATTER_FENCE:
            return fields
        key, sep, value = line.partition(":")
        if sep:
            fields[key.strip().lower()] = value.strip()
    return None


def _parse_markdown_header(lines: list[str]) -> dict[str, str]:
    """Read `# Meeting: x`, `Date:` and `Attendees:` lines from the top of the note."""
    fields: dict[str, str] = {}
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("## "):
            break
        if (m := _MEETING_TITLE_RE.match(stripped)) and "title" not in fields:
            fields["title"] = m.group("title")
        elif (m := _DATE_RE.match(stripped)) and "date" not in fields:
            fields["date"] = m.group("value")
        elif (m := _ATTENDEES_RE.match(stripped)) and "attendees" not in fields:
            fields["attendees"] = m.group("value")
    return fields


def _filename_date(file_name: str) -> date | None:
    match = _FILENAME_DATE_RE.match(file_name)
    return parse_header_date(match.group(1)) if match else None


def _resolve_date(fields: dict[str, str], file_name: str) -> tuple[date | None, tuple[str, ...]]:
    header_date = parse_header_date(fields.get("date", ""))
    if header_date is not None:
        return header_date, ()
    fallback = _filename_date(file_name)
    if fallback is not None:
        return fallback, (WARNING_DATE_FROM_FILENAME,)
    return None, ()


def read_note(path: Path, display_name: str | None = None) -> Note | SkippedNote:
    """Read one note; never raises for bad content."""
    name = display_name or path.name
    if path.suffix.lower() != MARKDOWN_SUFFIX:
        return SkippedNote(name, REASON_NOT_MARKDOWN)
    try:
        raw = path.read_bytes()
    except OSError as exc:
        return SkippedNote(name, f"cannot read file: {exc.strerror or exc}")
    if not raw.strip():
        return SkippedNote(name, REASON_EMPTY)
    text = _decode(raw)
    if text is None:
        return SkippedNote(name, REASON_NOT_UTF8)
    return _build_note(path, name, text)


def _build_note(path: Path, name: str, text: str) -> Note | SkippedNote:
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    fields = _parse_front_matter(lines) or _parse_markdown_header(lines)
    title = fields.get("title", "").strip()
    meeting_date, warnings = _resolve_date(fields, path.name)
    if not title and meeting_date is None:
        return SkippedNote(name, REASON_NO_HEADER)
    if not title:
        return SkippedNote(name, REASON_NO_TITLE)
    if meeting_date is None:
        return SkippedNote(name, REASON_NO_DATE)
    return Note(
        path=path,
        file=name,
        title=title,
        meeting_date=meeting_date,
        attendees=_split_attendees(fields.get("attendees", "")),
        lines=tuple(lines),
        warnings=warnings,
    )
