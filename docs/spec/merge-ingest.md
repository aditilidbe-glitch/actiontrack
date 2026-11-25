# Module spec: Duplicate merging and ingest

Part of the actiontrack spec. Index and shared context: [../spec.md](../spec.md).
Requirement IDs and wording are unchanged from the original single-file spec.

- **Source:** `src/actiontrack/merge.py`, `src/actiontrack/ingest.py`
- **Tests:** `tests/test_ingest.py`
- **Requirements:** R-ING-01, R-ING-02, R-DUP-01, R-DUP-02, R-DUP-03
- **Acceptance criteria:** 12

## Requirements

- **R-ING-01. `actiontrack ingest <folder>`** reads every `*.md` file directly in the folder (non-recursive by default; `--recursive` opt-in) and updates the store.
  - AC-ING-01.1: On `samples/notes/`, 32 of 36 files are ingested; 4 are skipped and reported (see R-ING-03).
  - AC-ING-01.2: Output ends with a summary: files seen / ingested / skipped, items new / updated / merged, warnings.
  - AC-ING-01.3: Missing folder → error message, exit code 1, store untouched.

- **R-ING-02. Idempotent.** Re-ingesting an unchanged folder changes nothing.
  - AC-ING-02.1: Ingest twice; item IDs, count, statuses and sources are identical after the second run, and it reports 0 new.
  - AC-ING-02.2: A manual `done` (R-DON-01) is never undone by re-ingest.

- **R-DUP-01. Merge repeated actions across meetings.** Two mentions merge when the owner key is equal (resolved full name, or the same ambiguous short name) and normalized texts are similar (lower-case, strip stopwords, due phrases and punctuation; token similarity ≥ threshold, default 0.6, tuned against the samples in planning).
  - AC-DUP-01.1: Revised-quote item (09-01 "Priya… by Friday", 09-08 "Priya N.… by Friday", 09-15 `[x]`) → one item, Priya Nair, done, three sources.
  - AC-DUP-01.2: "Karan to freeze invoice edits from 9 Oct" (09-29, 10-08) → one item with two sources.
  - AC-DUP-01.3: "Sam to confirm cloud budget with finance" (09-01, 09-15, 09-22 `[x]`) → one item, done.
  - AC-DUP-01.4: Similar-sounding but different items are not merged: "Sam to confirm cloud budget with finance" ≠ "Sam to confirm rollback plan".
  - AC-DUP-01.5: Same text, different resolved owners (Priya Nair vs Priya Shah) are never merged.

- **R-DUP-02. Latest status wins; due date is taken from the latest mention that has one.** The earliest source is the origin; all sources are kept.
  - AC-DUP-02.1: Wireframes item (09-01, 09-15, 09-22) shows the 09-22 due date; sources list all three.
  - AC-DUP-02.2: A later unchecked mention does not reopen a manually completed item; it is reported as a note.

- **R-DUP-03. Merges are reported** in the ingest summary (item, merged sources) so a wrong merge is visible.
