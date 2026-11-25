# Module spec: Note reading and headers

Part of the actiontrack spec. Index and shared context: [../spec.md](../spec.md).
Requirement IDs and wording are unchanged from the original single-file spec.

- **Source:** `src/actiontrack/notes.py`
- **Tests:** `tests/test_notes.py`
- **Requirements:** R-ING-03, R-ING-04
- **Acceptance criteria:** 8

## Requirements

- **R-ING-03. Malformed notes are skipped and reported, never fatal.** Each skip names the file and reason, and is listed in the summary.
  - AC-ING-03.1: `2026-09-09-notes-final-v2.md` (0 bytes) → skipped, reason `empty file`.
  - AC-ING-03.2: `scratch.md` (binary/non-UTF-8 content) → skipped, reason `not valid UTF-8 text`.
  - AC-ING-03.3: `untitled.md` (no title, no date, no attendees) → skipped, reason `no meeting header or date`. Its items are not tracked.
  - AC-ING-03.4: `2026-09-19-offsite-draft.txt` → not read (wrong extension); reported as `not a markdown note` when the folder is listed.
  - AC-ING-03.5: One bad file never prevents the other files from being ingested.

- **R-ING-04. Valid note = text file with a recognizable title and a resolvable meeting date.**
  - AC-ING-04.1: Title from `# Meeting: <title>` or front matter `title:`; date from a `Date:` line or front matter `date:`.
  - AC-ING-04.2: `2026-09-16-standup.md` (YAML front matter, attendees list) parses with the same result as the `# Meeting:` style.
  - AC-ING-04.3: If the header date is unparseable (`2026-10-03-sales-pipeline.md`: "sometime last week"), fall back to the `YYYY-MM-DD` filename prefix and emit a warning `meeting date taken from filename`. If neither is available, the note is skipped (see Open Question OQ-3).
