# Module spec: Due dates and status

Part of the actiontrack spec. Index and shared context: [../spec.md](../spec.md).
Requirement IDs and wording are unchanged from the original single-file spec.

- **Source:** `src/actiontrack/dates.py`
- **Tests:** `tests/test_dates.py`
- **Requirements:** R-DAT-01, R-DAT-02, R-DAT-03
- **Acceptance criteria:** 8

## Requirements

- **R-DAT-01. Due dates** are resolved relative to the meeting date to an absolute ISO date, keeping the raw phrase.
  - Supported: ISO (`2026-09-08`), `10 Sep`, `Oct 3rd`, `2 Oct`, `Wed 16 Sep`, `15 October`, weekday names (`by Friday`, `Mon`, `Wednesday`: next occurrence strictly after the meeting date), `tomorrow`, `EOD` / `EOD tomorrow`, `by tomorrow`, `end of next week` (Friday of next week), `end of month`, `next Tuesday` (that weekday of the next calendar week), `from 9 Oct`.
  - Year defaults to the meeting's year; if that puts the date before the meeting date, roll to the next year.
  - AC-DAT-01.1: `2026-09-01` meeting, "by Friday" → 2026-09-04.
  - AC-DAT-01.2: `2026-09-01`, "by 2026-09-08" → 2026-09-08. `2026-09-03`, "by 10 Sep" → 2026-09-10.
  - AC-DAT-01.3: `2026-09-30` offsite, "Oct 3rd" → 2026-10-03; "15 October" → 2026-10-15; "by 7 Oct" → 2026-10-07.
  - AC-DAT-01.4: `2026-09-22` (a Tuesday) "by Wednesday" → 2026-09-23. `2026-09-30` (a Wednesday) "by Wednesday" would be 2026-10-07 (strictly after the meeting date).

- **R-DAT-02. Vague or missing due dates are unknown, not guessed.** Raw text kept, `due = null`.
  - AC-DAT-02.1: "mid-October" (offsite, Sam's on-call rotation) → due null, raw `mid-October`, flagged `due vague`.
  - AC-DAT-02.2: Items with no date phrase (e.g. "Sam to rotate the staging credentials", "Rahul to estimate the SSO work") → due null.
  - AC-DAT-02.3: Items with null due are never `overdue`.

- **R-DAT-03. Status** is `done` (checked), `open` (unchecked, not past due), `overdue` (unchecked and due < today). "Today" is the system date, overridable with `--today YYYY-MM-DD` or env `ACTIONTRACK_TODAY` for reproducible tests.
  - AC-DAT-03.1: With `--today 2026-10-01`, an open item due 2026-09-30 is overdue; due 2026-10-01 is open; due null is open.
