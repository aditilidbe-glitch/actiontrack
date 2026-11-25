# Module spec: Action-item extraction

Part of the actiontrack spec. Index and shared context: [../spec.md](../spec.md).
Requirement IDs and wording are unchanged from the original single-file spec.

- **Source:** `src/actiontrack/extract.py`
- **Tests:** `tests/test_extract.py`
- **Requirements:** R-PAR-01, R-PAR-02, R-PAR-03, R-PAR-04, R-PAR-05, R-PAR-06
- **Acceptance criteria:** 6

## Requirements

- **R-PAR-01. Action items are checkbox lines under the `## Action items` section**, with markers `-`, `*`, `+`, any nesting depth, `[ ]` open, `[x]`/`[X]` done.
  - AC-PAR-01.1: `2026-10-02-finance-sync.md`: `[X]` is done; the `*` and `+` lines are parsed as open items.
  - AC-PAR-01.2: `2026-09-30-q4-offsite.md`: nested `Karan to validate targets…` is parsed as its own item with parent link; `*` and `+` items under "Morning" are parsed.

- **R-PAR-02. Markdown table rows** with columns Owner / Action / Due are parsed as items (all are open).
  - AC-PAR-02.1: Offsite note → item owner Anita, text "Refresh the brand kit", due 2026-10-09.

- **R-PAR-03. Checkboxes that are not agreed actions are excluded** (blockquotes `>`, fenced code blocks, HTML comments) and counted in the report as `excluded: quoted/code/comment`.
  - AC-PAR-03.1: `2026-09-21-incident-review.md`: the quoted `> - [ ] Karan to refund… by Friday` is excluded; the real list item `Karan to refund affected customers` is tracked (no due date).
  - AC-PAR-03.2: `2026-10-09-security-review.md`: the fenced `Owner to remediate finding…` and the commented-out `Sam to buy hardware tokens…` are excluded; 4 real items tracked.

- **R-PAR-04. Unsupported formats are detected, not silently dropped.** `ACTION:` lines are reported as `unsupported format: ACTION:` with file and line.
  - AC-PAR-04.1: Offsite note → the `ACTION: Karan to circulate the offsite summary tomorrow` line appears in the report as unsupported and is not tracked.

- **R-PAR-05. Checkboxes outside `## Action items`** (e.g. discussion prose, "Morning" sections of long notes) are tracked only if they are checkbox lines in a section whose heading is not Parking lot / Discussion-only; the offsite's checkbox lines under "Morning" and "Afternoon" are tracked (see OQ-5).

- **R-PAR-06. Item text is stored verbatim** (trimmed) together with source file and line number.
