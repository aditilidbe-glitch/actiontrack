"""U3 tests: note reading. Covers R-ING-03, R-ING-04, R-SAF-02."""

from __future__ import annotations

import hashlib
from datetime import date
from pathlib import Path

import pytest

from actiontrack import notes
from actiontrack.notes import Note, SkippedNote, discover, read_note

BASIC = """# Meeting: Quote portal kickoff
Date: 2026-09-01
Attendees: Priya Nair, Rahul Mehta, Anita Desai, Sam Okafor

## Action items
- [ ] Priya to send the revised quote to Acme by Friday
"""

FRONT_MATTER = """---
title: Team standup
date: 2026-09-16
attendees: [Anita Desai, Lena Fischer, Meera Iyer]
---

## Action items
- [ ] Lena to draft the case study outline by 2026-09-21
"""


def write(tmp_path: Path, name: str, content: str | bytes) -> Path:
    path = tmp_path / name
    if isinstance(content, bytes):
        path.write_bytes(content)
    else:
        path.write_text(content, encoding="utf-8", newline="")
    return path


def test_markdown_header_parses(tmp_path: Path) -> None:
    """AC-ING-04.1."""
    result = read_note(write(tmp_path, "2026-09-01-kickoff.md", BASIC))
    assert isinstance(result, Note)
    assert result.title == "Quote portal kickoff"
    assert result.meeting_date == date(2026, 9, 1)
    assert result.attendees == ("Priya Nair", "Rahul Mehta", "Anita Desai", "Sam Okafor")
    assert result.warnings == ()


def test_front_matter_matches_markdown_shape(tmp_path: Path) -> None:
    """AC-ING-04.2."""
    result = read_note(write(tmp_path, "2026-09-16-standup.md", FRONT_MATTER))
    assert isinstance(result, Note)
    assert (result.title, result.meeting_date) == ("Team standup", date(2026, 9, 16))
    assert result.attendees == ("Anita Desai", "Lena Fischer", "Meera Iyer")


@pytest.mark.parametrize(
    ("date_line", "expected"),
    [("9 September 2026", date(2026, 9, 9)), ("Monday, 14 September 2026", date(2026, 9, 14))],
)
def test_verbose_header_dates(tmp_path: Path, date_line: str, expected: date) -> None:
    content = f"# Meeting: X\nDate: {date_line}\nAttendees: A B\n"
    result = read_note(write(tmp_path, "note.md", content))
    assert isinstance(result, Note)
    assert result.meeting_date == expected


def test_unparseable_date_falls_back_to_filename_with_warning(tmp_path: Path) -> None:
    """AC-ING-04.3."""
    content = "# Meeting: Sales pipeline\nDate: sometime last week\nAttendees: A B\n"
    result = read_note(write(tmp_path, "2026-10-03-sales-pipeline.md", content))
    assert isinstance(result, Note)
    assert result.meeting_date == date(2026, 10, 3)
    assert notes.WARNING_DATE_FROM_FILENAME in result.warnings


def test_no_attendees_is_not_an_error(tmp_path: Path) -> None:
    content = "# Meeting: Team standup\nDate: 2026-09-23\n"
    result = read_note(write(tmp_path, "2026-09-23-standup.md", content))
    assert isinstance(result, Note)
    assert result.attendees == ()


def test_crlf_and_bom_are_handled(tmp_path: Path) -> None:
    data = ("﻿" + BASIC.replace("\n", "\r\n")).encode("utf-8")
    result = read_note(write(tmp_path, "2026-09-01-kickoff.md", data))
    assert isinstance(result, Note)
    assert result.title == "Quote portal kickoff"
    assert all("\r" not in line for line in result.lines)


@pytest.mark.parametrize(
    ("name", "content", "reason"),
    [
        ("empty.md", b"", notes.REASON_EMPTY),
        ("blank.md", b"  \n\n", notes.REASON_EMPTY),
        ("binary.md", b"\x89PNG\r\n\x1a\n\x00\x00data", notes.REASON_NOT_UTF8),
        ("badutf8.md", b"# Meeting: x\n\xff\xfe\xfa", notes.REASON_NOT_UTF8),
        ("untitled.md", b"- [ ] Sam to chase the vendor\n", notes.REASON_NO_HEADER),
        ("2026-09-01-x.md", b"just text, no header\n", notes.REASON_NO_TITLE),
        ("nodate.md", b"# Meeting: Something\nAttendees: A B\n", notes.REASON_NO_DATE),
        ("draft.txt", b"- [ ] Book the venue\n", notes.REASON_NOT_MARKDOWN),
    ],
)
def test_bad_files_are_skipped_with_reason(tmp_path: Path, name: str, content: bytes, reason: str) -> None:
    """AC-ING-03.1 .. 03.4: never raises."""
    result = read_note(write(tmp_path, name, content))
    assert result == SkippedNote(name, reason)


def test_unreadable_path_is_skipped_not_raised(tmp_path: Path) -> None:
    folder = tmp_path / "dir.md"
    folder.mkdir()
    result = read_note(folder)
    assert isinstance(result, SkippedNote)
    assert result.reason.startswith("cannot read file")


def test_reading_does_not_modify_the_file(tmp_path: Path) -> None:
    """AC-SAF-02.1."""
    path = write(tmp_path, "2026-09-01-kickoff.md", BASIC)
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    read_note(path)
    assert hashlib.sha256(path.read_bytes()).hexdigest() == before


def test_discover_lists_markdown_and_reports_others(tmp_path: Path) -> None:
    write(tmp_path, "a.md", BASIC)
    write(tmp_path, "b.txt", "x")
    sub = tmp_path / "sub"
    sub.mkdir()
    write(sub, "c.md", BASIC)
    paths, skipped = discover(tmp_path)
    assert [p.name for p in paths] == ["a.md"]
    assert skipped == [SkippedNote("b.txt", notes.REASON_NOT_MARKDOWN)]
    recursive, _ = discover(tmp_path, recursive=True)
    assert sorted(p.name for p in recursive) == ["a.md", "c.md"]


def test_real_samples_header_behaviour(samples_dir: Path) -> None:
    """AC-ING-03.1..03.3, AC-ING-04.2/04.3 on the real corpus."""
    by_name = {p.name: read_note(p) for p in samples_dir.glob("*.md")}
    assert by_name["2026-09-09-notes-final-v2.md"] == SkippedNote("2026-09-09-notes-final-v2.md", notes.REASON_EMPTY)
    assert by_name["scratch.md"].reason == notes.REASON_NOT_UTF8  # type: ignore[union-attr]
    assert by_name["untitled.md"].reason == notes.REASON_NO_HEADER  # type: ignore[union-attr]
    assert isinstance(by_name["2026-09-16-standup.md"], Note)
    fallback = by_name["2026-10-03-sales-pipeline.md"]
    assert isinstance(fallback, Note) and fallback.warnings
