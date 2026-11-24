# Plan: actiontrack CLI
**Date:** 2026-11-24
**Status:** draft
**Origin:** docs/spec.md (approved 2026-11-24)

## Context & Decisions

- Python 3.11+ with stdlib only at runtime (`argparse`, `json`, `re`, `datetime`, `hashlib`, `difflib`, `subprocess`); `pytest` is the only dev dependency. Chosen to keep the CLI installable anywhere with no supply-chain surface.
- Source layout is `src/actiontrack/` with one module per concern, tests in `tests/`, the console entry point is `actiontrack`. `python -m pytest -q` is the test command.
- Parsing is line-based with a small state machine (section tracking, fenced-code, HTML-comment and blockquote awareness), not a full markdown parser, so exclusions in R-PAR-03 are explicit and testable.
- Pure functions are separated from I/O. The parser, date resolver, owner resolver and merger take data and return data; only the store, ingest walker and Gmail adapter touch disk or processes. This lets unit tests run without the filesystem.
- "Today" is injected (`--today` / `ACTIONTRACK_TODAY`) everywhere status or relative dates are computed. No module reads the clock except the CLI entry point.
- Item IDs are `AT-` plus 6 hex characters from a hash of the origin item's owner key and normalized text. They are persisted, never recomputed, so merges and re-ingest keep them stable. Collisions extend the hash length.
- Merge similarity uses stopword/due-phrase stripping plus token-set similarity (default threshold 0.6, a config constant tuned against `samples/notes/` in U7). Merges never cross different resolved owners.
- Gmail access goes through an adapter interface with an allowlist of `create_draft` / `update_draft` / `get_draft` / `list_drafts`. Production adapter shells out to headless `claude -p` with `--allowedTools` restricted to the Gmail draft tools (decision OQ-1, confirmed by the user 2026-11-24). A fake adapter backs all tests. A file/dry-run adapter prints or writes the payload. The code never references send-type tool names except in a denylist constant checked by tests.
- OQ-2 to OQ-7 are NOT yet answered by the user. The spec's stated positions are used as working defaults (similarity merge with reporting, filename-date fallback with warning, no `assign` command, track checkboxes in the offsite note's sections, "Everyone" items list-only, roster emails supplied by the user, tests use `@example.com` fixtures). Tests affected if the user overrides: OQ-3 → U3; OQ-5 → U4; OQ-2 → U7; OQ-6 → U9. Each is isolated behind one rule so a change is cheap.
- Store schema (locked): top-level `{schema_version: 1, items: {id: Item}, drafts: {owner_key: draft_id}, notes: {path: checksum}}`. Exit codes are constants 0/1/2 defined in `models.py`. A newer-than-known `schema_version` is treated like an unknown one (refuse, never overwrite).
- Skills `.claude/skills/note-parsing` and `.claude/skills/followup-drafting` are written BEFORE U4 and U9 (project step 4); U9 tests the draft template defined in the followup-drafting skill.
- Ingest and follow-up reports have a fixed, line-oriented format, pinned by snapshot tests (also needed for byte-identical output, R-NFR-02).
- `samples/notes/` is the integration corpus and is never modified; unit tests use small inline strings or `tmp_path` copies.
- Every test docstring or marker lists the AC IDs it covers, so traceability is checkable by grep.

## Scope

**In scope:**
- `ingest`, `list`, `done`, `followup` commands per spec R-ING, R-PAR, R-OWN, R-DAT, R-DUP, R-LST, R-DON, R-FUP, R-SAF, R-STO, R-RPT, R-NFR.
- Roster file, JSON store, Gmail draft adapter with fake, dry-run.
- Two project skills (note parsing, follow-up drafting) in `.claude/skills/`, written after this plan and before U4/U9; they own the parsing rules summary and the draft voice/template (R-FUP-06).

**Out of scope:**
- Sending mail by any path; `assign` command; tracking `ACTION:` lines (reported only); non-markdown inputs; reminders/scheduling; calendar; multi-user sync; GUI.

## Implementation Units

- U1. **Project scaffold and domain models**: package skeleton, dataclasses for Note, Item, Source, Person, Store schema constants, shared test helpers (sample-corpus path, `tmp` store).
  - Files: `pyproject.toml`, `src/actiontrack/__init__.py`, `src/actiontrack/models.py`, `tests/conftest.py`, `tests/test_models.py`
  - Depends on: —
  - Spec: R-STO-01, R-RPT-01
  - Test scenarios:
    - Happy path (R-STO-01): an Item with owners, due, status and two sources round-trips to dict and back unchanged; `SCHEMA_VERSION == 1` and exit-code constants are 0/1/2 (R-RPT-01 constants only; behaviour is tested in U10).
    - Edge case (R-STO-01, R-DAT-02): an Item with `due=None`, raw due text, ambiguous owner candidates round-trips with those fields intact; models are immutable where declared.
    - Error path (R-STO-01): loading a dict with a missing required field raises a clear domain error (not KeyError).

- U2. **Date resolver**: turn raw due phrases into ISO dates relative to the meeting date; classify vague phrases as unknown.
  - Files: `src/actiontrack/dates.py`, `tests/test_dates.py`
  - Depends on: U1
  - Spec: R-DAT-01, R-DAT-02, R-DAT-03
  - Test scenarios:
    - Happy path (table-driven, AC-DAT-01.1..4): `2026-09-01` + "Friday" → 2026-09-04; "2026-09-08" → itself; "10 Sep" → 2026-09-10; "Oct 3rd" → 2026-10-03; "15 October" → 2026-10-15; "Wed 16 Sep" → 2026-09-16; "tomorrow", "EOD", "end of next week", "end of month", "next Tuesday", "from 9 Oct" all resolve per the weekday table; 2026-09-22 + "Wednesday" → 2026-09-23.
    - Edge case: weekday equal to meeting weekday goes to the following week (2026-09-30 + "Wednesday" → 2026-10-07); month-day before the meeting date rolls to next year; "Wed 16 Sep" whose weekday does not match the date is still accepted with a warning flag.
    - Error path: "mid-October", "soon", "next quarter", empty string → `None` with `vague=True`/raw preserved, never an exception; invalid dates such as "31 Feb" → unresolved, not a crash.
    - Status (AC-DAT-03.1): with today 2026-10-01, due 09-30 → overdue, due 10-01 → open, due None → open, checked → done regardless of date.

- U3. **Note reader and header parser**: read a file safely, detect skip reasons, parse title/date/attendees from `# Meeting:` + `Date:` or YAML-style front matter, filename-date fallback.
  - Files: `src/actiontrack/notes.py`, `tests/test_notes.py`
  - Depends on: U1, U2
  - Spec: R-ING-03, R-ING-04, R-SAF-02
  - Test scenarios:
    - Happy path: `2026-09-01-quote-portal-kickoff.md` → title "Quote portal kickoff", date 2026-09-01, four attendees; `2026-09-16-standup.md` (front matter, list attendees) yields the same shape (AC-ING-04.2); dates "9 September 2026" and "Monday, 14 September 2026" parse to ISO.
    - Edge case: `2026-10-03-sales-pipeline.md` ("sometime last week") → date from filename plus warning (AC-ING-04.3); note without Attendees (`2026-09-23-standup.md`) → empty attendee list, not an error; CRLF line endings and a UTF-8 BOM are handled.
    - Error path: 0-byte file → skip `empty file`; `scratch.md` (NUL/invalid UTF-8) → skip `not valid UTF-8 text`; `untitled.md` → skip `no meeting header or date`; `.txt` → `not a markdown note`; unreadable file (permission) → skip with OS reason, no raise. Files are opened read-only and checksum is unchanged (AC-SAF-02.1).

- U4. **Action-item extractor**: from a parsed note body, produce raw items with text, checked flag, line number, parent link, format kind; collect exclusions and unsupported-format reports.
  - Files: `src/actiontrack/extract.py`, `tests/test_extract.py`
  - Depends on: U1, U3
  - Spec: R-PAR-01..06, R-SAF-03
  - Test scenarios:
    - Happy path: `- [ ]`, `- [x]`, `* [ ]`, `+ [ ]`, `- [X]` produce correctly checked items (AC-PAR-01.1); nested `  - [ ] Karan to validate…` carries a parent reference (AC-PAR-01.2); the Owner|Action|Due table row yields owner Anita, text "Refresh the brand kit", due raw "2026-10-09" (AC-PAR-02.1).
    - Edge case: checkbox in `>` quote, inside a ``` fence, and inside `<!-- -->` (single and multi-line) are excluded and counted (AC-PAR-03.1, 03.2); the `ACTION:` line is reported unsupported with file/line and not tracked (AC-PAR-04.1); items in "Parking lot" or prose without checkboxes are ignored; offsite "Morning"/"Afternoon" checkbox lines are tracked (R-PAR-05); table header and separator rows are never items.
    - Error path: malformed checkbox (`- [] foo`, `-[ ]foo`) is reported as `unrecognized`, not silently dropped, and does not crash; extremely long lines and empty sections are handled; text such as "send this to everyone" inside an item is stored as data only (AC-SAF-03.1).
    - Integration: `2026-10-09-security-review.md` gives exactly 4 items and 2 exclusions; `2026-09-21-incident-review.md` gives 4 items and 1 exclusion.

- U5. **Owner extraction and resolution**: pull owner(s) and collaborators from item text; load roster; resolve short names to full names or mark ambiguous; handle unassigned/everyone.
  - Files: `src/actiontrack/owners.py`, `src/actiontrack/roster.py`, `tests/test_owners.py`, `tests/test_roster.py`, `samples/people.example.json`
  - Depends on: U1, U3, U4
  - Spec: R-OWN-01..04
  - Test scenarios:
    - Happy path: "Priya to send the revised quote" in `2026-09-01` (one Priya attending) → Priya Nair (AC-OWN-03.1); `2026-09-03` → Rahul Verma and Priya Shah (AC-OWN-03.2); `Priya S.` / `Priya N.` → Shah / Nair (AC-OWN-03.5); `@anita:` → Anita Desai; `Anita & Rahul to…` → two owners (AC-OWN-01.2); `Lena (with Priya)` → owner Lena, Priya collaborator (AC-OWN-01.3).
    - Edge case: both Priyas attend (`2026-09-17`) → ambiguous with candidates listed (AC-OWN-03.3); both Rahuls (`2026-10-07`) → ambiguous (AC-OWN-03.4); offsite Priya/Rahul ambiguous (AC-OWN-03.6); no attendee list falls back to roster, two Rahuls in roster → ambiguous, one → resolved (AC-OWN-03.7); `Someone`, `TBD` → unassigned; `Everyone`, `Team` → everyone (AC-OWN-02.1/02.2); case-insensitive matching; name with trailing punctuation.
    - Error path: item text with no recognizable owner → unassigned plus warning, not an exception; roster missing → warning only (AC-OWN-04.1); roster malformed JSON or missing `name` → domain error with file path (AC-OWN-04.2); roster duplicate full names → rejected with message.

- U6. **Store and ID allocation**: JSON store with atomic writes, schema version, stable short IDs, draft-id map per owner.
  - Files: `src/actiontrack/store.py`, `tests/test_store.py`
  - Depends on: U1
  - Spec: R-STO-01, R-DON-01 (persistence), R-FUP-04 (draft ids)
  - Test scenarios:
    - Happy path: save then load returns identical data; IDs have format `AT-xxxxxx` and are unique across 500 generated items; default path `.actiontrack/store.json` is created on first write.
    - Edge case: ID collision handled by lengthening, and the result is deterministic; concurrent-looking double save leaves a valid file; empty store loads as empty; unique-prefix lookup works and an ambiguous prefix raises with candidates (AC-DON-01.3).
    - Error path: simulated failure between temp write and rename leaves the old file intact (AC-STO-01.1); corrupt JSON, an unknown `schema_version` (e.g. 0 or 99) and a newer-than-known version each raise an error that never overwrites the file (AC-STO-01.2); read-only directory gives a clear error.
    - Store location (R-STO-01): `--store <custom path>` round-trips and creates missing parent directories.
    - Draft map (R-FUP-04): the `drafts` map stores, reads, replaces and removes one draft id per owner key and persists across save/load.

- U7. **Merge and ingest orchestration**: walk the folder, run U3–U5 per note, merge duplicates into tracked items, update the store idempotently, produce the ingest report.
  - Files: `src/actiontrack/merge.py`, `src/actiontrack/ingest.py`, `tests/test_merge.py`, `tests/test_ingest.py`
  - Depends on: U2, U3, U4, U5, U6
  - Spec: R-ING-01, R-ING-02, R-ING-03, R-DUP-01..03, R-DON-01 (manual done sticks)
  - Test scenarios:
    - Happy path (AC-ING-01.1): ingesting `samples/notes/` yields 32 notes ingested and 4 skipped with the reasons from AC-ING-03.1..04; revised-quote item merges to one done Priya Nair item with three sources (AC-DUP-01.1); freeze-invoice-edits merges to two sources (AC-DUP-01.2); cloud-budget item done (AC-DUP-01.3); wireframes item shows the 09-22 due (AC-DUP-02.1).
    - Edge case: re-ingest is a no-op (same IDs, counts, statuses, 0 new) (AC-ING-02.1); a manually done item stays done when a later note lists it open, with a note in the report (AC-ING-02.2, AC-DUP-02.2); "confirm cloud budget" vs "confirm rollback plan" not merged (AC-DUP-01.4); same text with Priya Nair vs Priya Shah not merged (AC-DUP-01.5); merged items reported with their sources (AC-DUP-03); a later mention with no due keeps the earlier due.
    - Error path: one corrupt file among valid ones does not stop ingest (AC-ING-03.5); missing folder → error, exit code mapped later, store untouched (AC-ING-01.3); the store is not written if ingest aborts mid-way; the threshold is a single constant, with boundary tests: a synthetic pair scoring exactly at the threshold merges and one just below does not, and named sample pairs must stay on the right side (must merge: "set up staging" vs "set up the staging environment"; "send revised quote to Acme" vs "send the revised quote to Acme"; must not merge: "confirm cloud budget with finance" vs "confirm rollback plan"; "review the schema mapping doc" vs "review the welcome email for accessibility"). If retuning flips any of these, the test fails and the change needs review.
    - Report format (AC-ING-01.2, R-NFR-02): the ingest summary is pinned by a snapshot test on the sample corpus with a fixed `--today`.

- U8. **List and done commands (logic layer)**: filters, sorting, owner-name handling, JSON output, `done` transitions.
  - Files: `src/actiontrack/query.py`, `tests/test_query.py`
  - Depends on: U2, U5, U6, U7
  - Spec: R-LST-01, R-LST-02, R-DON-01, R-DAT-03
  - Test scenarios:
    - Happy path: `--status overdue` with today 2026-10-20 returns only open items with due before that date (AC-LST-01.1); `--owner "Priya Nair"` returns her items plus the ambiguous-exclusion footer (AC-LST-02.1); results sort by due (nulls last) then owner (AC-LST-01.4); `done <id>` sets done and `--status open` omits it (AC-DON-01.1).
    - Edge case: `--due-before` is strictly before and excludes null-due items with a count (AC-LST-01.2); combined filters AND together; `--owner unassigned` / `everyone` work, case-insensitive (AC-LST-02.3); `done` on an already-done item is a no-op message (AC-DON-01.2); joint-owner item appears under each owner.
    - Error path: `--owner Priya` ambiguous → ambiguity error with candidates (AC-LST-02.2); unknown owner → not-found error (AC-LST-02.4); invalid status or malformed date → usage error (AC-LST-01.3); unknown or ambiguous id on `done` → error, store unchanged.

- U9. **Follow-up drafting and Gmail adapter**: compose the draft, adapter interface with allowlist, fake, dry-run and headless `claude -p` adapter, draft-id bookkeeping.
  - Files: `src/actiontrack/followup.py`, `src/actiontrack/gmail.py`, `tests/test_followup.py`, `tests/test_gmail.py`, `tests/test_no_send.py`
  - Depends on: U5, U6, U8
  - Spec: R-FUP-01..06, R-SAF-01
  - Test scenarios:
    - Happy path: `followup "Karan Joshi"` with the fake adapter → exactly one `create_draft`, zero send calls (AE6); subject `Follow-up: N open action items`; body groups open items by meeting, shows due or "no due date", marks overdue, omits done (AC-FUP-01.1); roster email lands in To; output says "DRAFT created, not sent" with the draft id (AC-FUP-01.2); second run calls `update_draft` with the stored id (AC-FUP-04.1).
    - Edge case: no roster email → draft created with empty To and `NO RECIPIENT` flag (R-FUP-03); owner with no open items → no draft, exit 0 (AC-FUP-01.3); ambiguous-owner items excluded with a count (AC-FUP-02.2); `--dry-run` prints payload and makes zero adapter calls (R-FUP-05); stored draft id no longer exists in Gmail → create a new one.
    - Template (R-FUP-06): the body matches the template in the followup-drafting skill (greeting, grouped list, closing) and snapshot-tests against a fixed store; every fact in the body (owner, item text, due, meeting title, file name) is traceable to a store field, checked by asserting no tokens outside template + store values; the fake adapter's recorded payload is the only thing sent to the adapter (R-FUP-05.2: a guard test fails if the real adapter is constructed under pytest).
    - Error path: `followup Priya` with two Priyas → no draft (AC-FUP-02.1); `(unassigned)`/`(everyone)` rejected; adapter failure or `claude` binary missing → clear error, store unchanged, suggests `--dry-run` (AC-FUP-05.1); the allowlist adapter raises on `send_message`, `reply`, `forward` (AC-SAF-01.2); a source-tree scan test fails if a denylisted tool name appears outside the denylist constant (AC-SAF-01.3); note text with injected instructions appears only as quoted item text (AC-SAF-03.1); the headless call builds its command with only the two draft tools in `--allowedTools` (asserted on the argv, with `subprocess` mocked).

- U10. **CLI wiring, reporting and end-to-end checks**: argparse commands, exit codes, stdout/stderr split, `--today`, `--store`, `--people`, `--json`; end-to-end run on the real samples.
  - Files: `src/actiontrack/cli.py`, `src/actiontrack/__main__.py`, `tests/test_cli.py`, `tests/test_e2e_samples.py`
  - Depends on: U7, U8, U9
  - Spec: R-RPT-01, R-NFR-01..03, AE1–AE6
  - Test scenarios:
    - Happy path: AE1–AE6 run through the real CLI against a `tmp_path` copy of `samples/notes/` with the fake Gmail adapter; ingest summary shows files seen/ingested/skipped, new/updated/merged, warnings.
    - Edge case: identical stdout across two runs with the same `--today` (R-NFR-02); ingest of 36 files completes in under 2 seconds (R-NFR-01); `--json` output parses; env var `ACTIONTRACK_TODAY` overridden by `--today`; checksums of `samples/notes/` unchanged after the whole e2e run.
    - Error path: exit 1 on errors, 2 on usage/ambiguity, 0 otherwise, messages on stderr (R-RPT-01); unknown subcommand prints usage; coverage run `pytest --cov` reaches at least 85% (R-NFR-03).

## Risks & Dependencies

- **Date and similarity heuristics may be wrong on real notes.** Mitigation: table-driven tests from the samples, merges and vague dates always reported, thresholds as named constants, no silent guesses.
- **Headless `claude -p` Gmail path depends on local Claude Code install, auth and connector state.** Mitigation: adapter interface, `--dry-run`, tests never call it, argv asserted, clear failure message. First real draft is verified manually by the user, not by CI.
- **Accidental send path.** Mitigation: allowlist adapter, denylist scan test, fake adapter raising on any non-draft call, `CLAUDE.md` hard rule.
- **Ambiguous owners reduce usefulness of follow-ups.** Mitigation: explicit reporting; `assign` command is a candidate follow-up if the user wants it (OQ-4).
- **Store corruption or schema drift.** Mitigation: atomic writes, versioned schema, never overwrite an unreadable store.
- **Skills not yet written when U4/U9 start.** Mitigation: plan order puts skills first; U9 cannot start until the followup-drafting template exists.
- **Windows path and encoding differences** (CRLF, BOM, console encoding). Mitigation: explicit UTF-8 I/O, tests for CRLF/BOM, `pathlib` everywhere.
- Dependency order: U1 → (U2, U6 in parallel) → U3 → U4 → U5 → U7 → U8 → U9 → U10.

## Open Questions

- [ ] OQ-2: confirm similarity-based merging is acceptable, or require interactive confirmation (spec default stands).
- [ ] OQ-3: confirm filename-date fallback for `2026-10-03-sales-pipeline.md`.
- [ ] OQ-4: add `assign` command later?
- [ ] OQ-5: confirm tracking of checkboxes under the offsite's Morning/Afternoon headings.
- [ ] OQ-6: "Everyone" items list-only (default) or fan-out.
- [ ] OQ-7: user supplies the real `people.json`; the repo ships only `samples/people.example.json`.
