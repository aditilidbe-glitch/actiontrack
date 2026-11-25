# actiontrack: Specification

**Date:** 2026-11-24
**Status:** APPROVED 2026-11-24 by the user. Open questions OQ-1..7 resolved 2026-11-24 (see section 6).
**Structure:** Restructured 2026-11-25 into per-module specs under `docs/spec/`; requirement IDs and wording unchanged.
**Language/stack:** Python 3.11+, stdlib `argparse`, `pytest`.

## 1. Problem statement

Action items from meetings live in scattered markdown notes. People re-state the same item across meetings, owners are named by first name only (two Priyas, two Rahuls), dates are relative ("by Friday"), and nobody can answer "what is open, who owns it, what is overdue?". `actiontrack` ingests the notes, keeps one tracked list, and drafts (never sends) a Gmail follow-up per owner, so a human reviews and sends each one.

## 2. Actors

- **A1. Note owner / PM**: runs the CLI, reviews drafts, sends them manually from Gmail.
- **A2. Action owner**: a named person who receives the follow-up (via a draft the PM sends).
- **A3. Gmail MCP connector**: external service. Only draft tools are permitted.

## 3. Scope

In: the four commands, a roster file, local JSON store, Gmail **draft** creation.
Out (this iteration): sending email in any form; editing note files; calendar integration; reminders/scheduling; multi-user sync; ACTION:-prefixed lines (detected and reported, not tracked); non-markdown files; a UI.

## 4. Requirements (per-module specs)

The requirements and acceptance criteria live in one spec file per module under `docs/spec/`. IDs are stable and unchanged. This table is the traceability index: requirement to module to source to tests.

| Module spec | Requirement IDs | Source | Tests |
|---|---|---|---|
| [Safety (cross-cutting)](spec/safety.md) | R-SAF-01, R-SAF-02, R-SAF-03 | `gmail.py`, `followup.py`, `notes.py`, `extract.py` | `test_followup.py`, `test_notes.py`, `test_extract.py`, `test_ingest.py` |
| [Note reading and headers](spec/notes.md) | R-ING-03, R-ING-04 | `notes.py` | `test_notes.py` |
| [Action-item extraction](spec/extract.md) | R-PAR-01, R-PAR-02, R-PAR-03, R-PAR-04, R-PAR-05, R-PAR-06 | `extract.py` | `test_extract.py` |
| [Owners, roster and same-first-name resolution](spec/owners.md) | R-OWN-01, R-OWN-02, R-OWN-03, R-OWN-04 | `owners.py`, `roster.py` | `test_owners.py` |
| [Due dates and status](spec/dates.md) | R-DAT-01, R-DAT-02, R-DAT-03 | `dates.py` | `test_dates.py` |
| [Duplicate merging and ingest](spec/merge-ingest.md) | R-ING-01, R-ING-02, R-DUP-01, R-DUP-02, R-DUP-03 | `merge.py`, `ingest.py` | `test_ingest.py` |
| [Store and domain models](spec/store.md) | R-STO-01 | `store.py`, `models.py` | `test_store.py`, `test_models.py` |
| [List, done and assign](spec/query.md) | R-LST-01, R-LST-02, R-DON-01, R-OWN-05 | `query.py` | `test_query.py` |
| [Follow-up drafting and Gmail adapters](spec/followup.md) | R-FUP-01, R-FUP-02, R-FUP-03, R-FUP-04, R-FUP-05, R-FUP-06 | `followup.py`, `gmail.py` | `test_followup.py` |
| [CLI, reporting and non-functional](spec/cli.md) | R-RPT-01, R-NFR-01, R-NFR-02, R-NFR-03 | `cli.py`, `__main__.py` | `test_cli.py` |

Unit-to-module mapping and test scenarios: see `docs/plans/`.

## 5. Acceptance examples (end to end on `samples/notes/`)

- **AE1.** `ingest samples/notes` → 32 ingested, 4 skipped (empty, binary, no header, .txt) with reasons, 1 `ACTION:` line reported unsupported, quoted/code/comment checkboxes excluded, no crash.
- **AE2.** `list --owner "Priya Nair" --status open --today 2026-10-01` → merged revised-quote item is not shown (done); footer reports ambiguous-Priya items excluded.
- **AE3.** `list --owner Priya` → exit 2 with candidates.
- **AE4.** `done <id>` for the "Meera to ask Acme for procurement contact" item, then `list --status open` no longer shows it.
- **AE5.** `followup "Karan Joshi" --dry-run` → draft with Karan's open items grouped by meeting, overdue marked, plus `NO RECIPIENT` if the roster has no email.
- **AE6.** `followup "Karan Joshi"` with the fake Gmail adapter → exactly one `create_draft` call, zero send calls.

## 6. Decisions on open questions (resolved 2026-11-24)

- **OQ-1.** Gmail access via a headless `claude -p` call limited to the draft tools; `--dry-run` as fallback. Not yet exercised against real Gmail.
- **OQ-2.** Similarity-based merging is kept (threshold 0.6, every merge reported).
- **OQ-3.** Filename-date fallback is kept, with a warning on every ingest.
- **OQ-4.** An `assign` command is added (R-OWN-05).
- **OQ-5.** All checkboxes are tracked except those under a "Parking lot" heading.
- **OQ-6.** "Everyone" items are list-only; never included in follow-ups.
- **OQ-7.** The user creates a local `people.json` (git-ignored); the repo ships only `samples/people.example.json`.
