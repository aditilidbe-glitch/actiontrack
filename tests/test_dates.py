"""U2 tests: due-date resolution. Covers R-DAT-01, R-DAT-02, R-DAT-03."""

from __future__ import annotations

from datetime import date

import pytest

from actiontrack.dates import (
    STATUS_DONE,
    STATUS_OPEN,
    STATUS_OVERDUE,
    compute_status,
    extract_due_phrase,
    parse_header_date,
    resolve_due,
)


def d(iso: str) -> date:
    return date.fromisoformat(iso)


@pytest.mark.parametrize(
    ("meeting", "phrase", "expected"),
    [
        # AC-DAT-01.1 / 01.2 / 01.3
        ("2026-09-01", "Friday", "2026-09-04"),
        ("2026-09-01", "2026-09-08", "2026-09-08"),
        ("2026-09-03", "10 Sep", "2026-09-10"),
        ("2026-09-30", "Oct 3rd", "2026-10-03"),
        ("2026-09-30", "15 October", "2026-10-15"),
        ("2026-09-30", "7 Oct", "2026-10-07"),
        ("2026-09-14", "Wed 16 Sep", "2026-09-16"),
        ("2026-09-01", "Thursday", "2026-09-03"),
        ("2026-09-01", "Wed", "2026-09-02"),
        ("2026-09-01", "Mon", "2026-09-07"),
        # AC-DAT-01.4
        ("2026-09-22", "Wednesday", "2026-09-23"),
        # relative phrases
        ("2026-09-01", "tomorrow", "2026-09-02"),
        ("2026-09-01", "by tomorrow", "2026-09-02"),
        ("2026-09-01", "EOD", "2026-09-01"),
        ("2026-09-21", "EOD tomorrow", "2026-09-22"),
        ("2026-09-03", "end of next week", "2026-09-11"),
        ("2026-09-14", "end of month", "2026-09-30"),
        ("2026-10-05", "next Tuesday", "2026-10-13"),
        ("2026-09-29", "9 Oct", "2026-10-09"),
        ("2026-09-02", "September 9, 2026", "2026-09-09"),
    ],
)
def test_resolve_due_happy_paths(meeting: str, phrase: str, expected: str) -> None:
    result = resolve_due(phrase, d(meeting))
    assert result.iso == expected
    assert result.vague is False
    assert result.raw == phrase


def test_weekday_equal_to_meeting_weekday_goes_to_next_week() -> None:
    """AC-DAT-01.4: strictly after the meeting date."""
    assert resolve_due("Wednesday", d("2026-09-30")).iso == "2026-10-07"


def test_month_day_before_meeting_rolls_to_next_year() -> None:
    assert resolve_due("2 Sep", d("2026-09-03")).iso == "2027-09-02"


def test_weekday_mismatch_is_accepted_with_warning() -> None:
    result = resolve_due("Thu 16 Sep", d("2026-09-14"))
    assert result.iso == "2026-09-16"
    assert result.warning is not None


@pytest.mark.parametrize("phrase", ["mid-October", "mid October", "soon", "next quarter", "31 Feb", "2026-13-45"])
def test_vague_or_invalid_phrases_are_unknown(phrase: str) -> None:
    """AC-DAT-02.1: never guess, never raise."""
    result = resolve_due(phrase, d("2026-09-30"))
    assert result.iso is None
    assert result.vague is True
    assert result.raw == phrase


@pytest.mark.parametrize("phrase", [None, "", "   "])
def test_no_phrase_means_no_due_and_not_vague(phrase: str | None) -> None:
    """AC-DAT-02.2."""
    result = resolve_due(phrase, d("2026-09-30"))
    assert (result.iso, result.raw, result.vague) == (None, None, False)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Priya to send the revised quote to Acme by Friday", "Friday"),
        ("Rahul to set up the staging environment by 2026-09-08", "2026-09-08"),
        ("Priya N. to send revised quote to Acme — by Friday", "Friday"),
        ("Lena to run the customer survey, results due 15 October", "15 October"),
        ("Sam to propose the on-call rotation by mid-October", "mid-October"),
        ("Karan to freeze invoice edits from 9 Oct", "9 Oct"),
        ("Sam to write the postmortem by EOD tomorrow", "EOD tomorrow"),
        ("Priya to write acceptance tests by 18 Sep", "18 Sep"),
        ("Anita to finalise the copy by Wed 16 Sep", "Wed 16 Sep"),
        ("Sam to cut cloud costs by 10% — proposal by 2026-10-09", "2026-10-09"),
        ("Meera to demo the portal to Acme on 2026-10-14", "2026-10-14"),
        ("Priya to collect feedback from Acme by 2026-10-20", "2026-10-20"),
        ("Priya to write the test plan by end of next week", "end of next week"),
        ("Lena to collect quotes by end of month", "end of month"),
        ("Rahul to start SSO spike by next Tuesday", "next Tuesday"),
        ("Karan to send the contract to legal by tomorrow", "tomorrow"),
    ],
)
def test_extract_due_phrase(text: str, expected: str) -> None:
    found = extract_due_phrase(text)
    assert found is not None
    assert found.text == expected
    assert text[found.start : found.end] == expected


@pytest.mark.parametrize(
    "text",
    [
        "Sam to rotate the staging credentials",
        "Rahul to estimate the SSO work",
        "Sam to cut cloud costs by 10%",
        "Meera to get a month of data from Acme",
        "",
    ],
)
def test_extract_due_phrase_none_when_absent(text: str) -> None:
    assert extract_due_phrase(text) is None


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("2026-09-01", "2026-09-01"),
        ("9 September 2026", "2026-09-09"),
        ("Monday, 14 September 2026", "2026-09-14"),
        ("September 9, 2026", "2026-09-09"),
    ],
)
def test_parse_header_date(text: str, expected: str) -> None:
    assert parse_header_date(text) == d(expected)


@pytest.mark.parametrize("text", ["sometime last week", "", "Friday", "9 September", "2026-02-30"])
def test_parse_header_date_unparseable_returns_none(text: str) -> None:
    assert parse_header_date(text) is None


def test_status_rules() -> None:
    """AC-DAT-03.1."""
    today = d("2026-10-01")
    assert compute_status(False, "2026-09-30", today) == STATUS_OVERDUE
    assert compute_status(False, "2026-10-01", today) == STATUS_OPEN
    assert compute_status(False, None, today) == STATUS_OPEN
    assert compute_status(True, "2026-09-01", today) == STATUS_DONE
