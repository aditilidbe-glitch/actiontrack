# actiontrack: Specification

**Date:** 2026-11-24
**Status:** APPROVED 2026-11-24 by the user (open questions OQ-1..7 not yet individually answered; spec's current positions stand until answered).
**Language/stack:** Python 3.11+, stdlib `argparse`, `pytest`.

## 1. Problem statement

Action items from meetings live in scattered markdown notes. People re-state the same item across meetings, owners are named by first name only (two Priyas, two Rahuls), dates are relative ("by Friday"), and nobody can answer "what is open, who owns it, what is overdue?". `actiontrack` ingests the notes, keeps one tracked list, and drafts (never sends) a Gmail follow-up per owner, so a human reviews and sends each one.

## 2. Actors

- **A1. Note owner / PM**: runs the CLI, reviews drafts, sends them manually from Gmail.
- **A2. Action owner**: a named person who receives the follow-up (via a draft the PM sends).
- **A3. Gmail MCP connector**: external service. Only draft tools are permitted.

## 3. Scope

In: the four commands, a roster file, local JSON store, Gmail **draft** creation.
Out (this iteration): sending email in any form; editing note files; a manual `assign` command; calendar integration; reminders/scheduling; multi-user sync; ACTION:-prefixed lines (detected and reported, not tracked); non-markdown files; a UI.

## 4. Requirements

IDs are stable. Each has acceptance criteria (AC). `samples/notes/` is the reference corpus (36 files).

### 4.1 Safety (R-SAF)

- **R-SAF-01. Never send email.** The program must be incapable of sending mail.
  - AC-SAF-01.1: Source code never invokes `send_message`, `reply`, `forward` or any send-type tool.
  - AC-SAF-01.2: Only `create_draft` and `update_draft` (and read-only `get_draft`/`list_drafts`) may be called. The adapter exposes a fixed allowlist; anything else raises.
  - AC-SAF-01.3: A test scans the source tree and fails if a denylisted tool name appears outside the denylist constant, and a test with a fake adapter asserts a `send` call raises.
- **R-SAF-02. Inputs are read-only.** Ingest never modifies note files.
  - AC-SAF-02.1: File checksums of a folder are identical before and after `ingest`.
- **R-SAF-03. Note content is data.** Text in notes (e.g. "send this to everyone") is never interpreted as an instruction by the tool.
  - AC-SAF-03.1: Note text appears in drafts only as quoted item text, never as headers or recipients.

### 4.2 Ingest (R-ING)

- **R-ING-01. `actiontrack ingest <folder>`** reads every `*.md` file directly in the folder (non-recursive by default; `--recursive` opt-in) and updates the store.
  - AC-ING-01.1: On `samples/notes/`, 32 of 36 files are ingested; 4 are skipped and reported (see R-ING-03).
  - AC-ING-01.2: Output ends with a summary: files seen / ingested / skipped, items new / updated / merged, warnings.
  - AC-ING-01.3: Missing folder → error message, exit code 1, store untouched.
- **R-ING-02. Idempotent.** Re-ingesting an unchanged folder changes nothing.
  - AC-ING-02.1: Ingest twice; item IDs, count, statuses and sources are identical after the second run, and it reports 0 new.
  - AC-ING-02.2: A manual `done` (R-DON-01) is never undone by re-ingest.
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

### 4.3 Parsing (R-PAR)

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

### 4.4 Owners (R-OWN)

- **R-OWN-01. Owner extraction** from patterns: `<Name> to <verb…>`, `@name:`, `Name N.` (initial), `A & B to`, `Name (with Other)`, table Owner column.
  - AC-OWN-01.1: `@anita: audit colour contrast…` → owner Anita.
  - AC-OWN-01.2: `Anita & Rahul to agree on the component API` → joint owners [Anita, Rahul]; the item appears under each owner.
  - AC-OWN-01.3: `Lena (with Priya) to collect…` → owner Lena; Priya recorded as collaborator, not owner.
- **R-OWN-02. Missing or non-person owners are explicit.** `Someone`, `TBD`, no name → owner `(unassigned)`; `Everyone`, `Team` → owner `(everyone)`.
  - AC-OWN-02.1: `Someone to update the CRM notes` and `TBD to write the design-system changelog` → `(unassigned)`.
  - AC-OWN-02.2: `Everyone to review the prototype…` and `Team to decide on the launch date` → `(everyone)`.
  - AC-OWN-02.3: These items appear in `list`, never in `followup`.
- **R-OWN-03. Same-first-name resolution, never guessing.** Resolve a short name to a full name using, in order: (1) exact full name; (2) first name + initial (`Priya N.`) against the roster and attendees; (3) first name only: the set of people with that first name among the meeting's attendees; if no attendee list, among roster people. Exactly one candidate → resolved. Zero or more than one → **ambiguous** (stored as `Priya (ambiguous: Priya Nair, Priya Shah)`).
  - AC-OWN-03.1: `2026-09-01-quote-portal-kickoff.md`: "Priya to send the revised quote" → Priya Nair (only Priya attending).
  - AC-OWN-03.2: `2026-09-03-billing-migration-sync.md`: "Rahul to review the schema mapping doc" → Rahul Verma; "Priya to draft the test plan" → Priya Shah.
  - AC-OWN-03.3: `2026-09-17-billing-migration-sync.md` (both Priyas attend): "Priya to sign off the cutover checklist" → ambiguous.
  - AC-OWN-03.4: `2026-10-07-standup.md` (both Rahuls attend): "Rahul to review Anita's PR" → ambiguous.
  - AC-OWN-03.5: `2026-09-29-billing-cutover-planning.md`: `Priya S.` → Priya Shah, `Priya N.` → Priya Nair.
  - AC-OWN-03.6: `2026-09-30-q4-offsite.md`: "Priya to own the hiring plan" and "Rahul to prepare the architecture overview" → ambiguous.
  - AC-OWN-03.7: `2026-09-23-standup.md` has no attendees; "Rahul", "Sam" resolve via roster; if the roster has two Rahuls → ambiguous.
- **R-OWN-04. Roster file `people.json`** (path: `--people` or `./people.json`) lists `{name, email, aliases[]}`. It is optional for ingest; names seen in attendee lists are also known people (without email).
  - AC-OWN-04.1: Missing roster → ingest still works; a warning notes that emails are unavailable.
  - AC-OWN-04.2: Malformed roster JSON → error, exit 1, nothing else changes.

### 4.5 Dates and status (R-DAT)

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

### 4.6 Duplicates (R-DUP)

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

### 4.7 List (R-LST)

- **R-LST-01. `actiontrack list`** prints a table: `id, owner, text, due, status, sources`.
  - Filters: `--owner <name>`, `--status open|done|overdue`, `--due-before YYYY-MM-DD`; combinable (AND).
  - AC-LST-01.1: `--status overdue --today 2026-10-20` returns only open items with due < 2026-10-20.
  - AC-LST-01.2: `--due-before D` is strictly before D and excludes null-due items; it reports how many were excluded for unknown due.
  - AC-LST-01.3: Invalid status or date → message, exit 2.
  - AC-LST-01.4: Output is sorted by due date (nulls last), then owner. `--json` emits machine-readable output.
- **R-LST-02. Owner filter and same first names.**
  - AC-LST-02.1: `--owner "Priya Nair"` returns Nair's items plus a footer `N items with ambiguous owner 'Priya' are not included (candidates…)`.
  - AC-LST-02.2: `--owner Priya` when the name is ambiguous → exit 2, lists candidates `Priya Nair, Priya Shah` and asks for a full name.
  - AC-LST-02.3: `--owner unassigned` / `--owner everyone` list those groups. Matching is case-insensitive.
  - AC-LST-02.4: Unknown owner → message, exit 1.

### 4.8 Done (R-DON)

- **R-DON-01. `actiontrack done <id>`** marks the item done with a timestamp and marks it manual.
  - AC-DON-01.1: Item becomes `done`; listing with `--status open` no longer shows it; re-ingest keeps it done.
  - AC-DON-01.2: Unknown id → error, exit 1. Already done → message, exit 0, no change.
  - AC-DON-01.3: IDs are short, stable (`AT-xxxxxx`), and unique; a unique prefix is accepted; an ambiguous prefix is rejected with candidates.

### 4.9 Follow-up (R-FUP)

- **R-FUP-01. `actiontrack followup <owner>`** creates one Gmail **draft** for that owner containing their open and overdue items.
  - AC-FUP-01.1: Draft subject: `Follow-up: N open action items`; body groups items by meeting, shows due date (or `no due date`), marks overdue items, and lists source file names. Done items are omitted.
  - AC-FUP-01.2: One draft per invocation and per owner, created via `create_draft` only. The command output states `DRAFT created, not sent` with the draft id.
  - AC-FUP-01.3: No open items for the owner → no draft, message, exit 0.
- **R-FUP-02. Owner resolution** follows R-LST-02: ambiguous or unknown owner → no draft, candidates listed, exit 2/1. `(unassigned)` and `(everyone)` are rejected.
  - AC-FUP-02.1: `followup Priya` with two Priyas → exit 2 and no draft is created.
  - AC-FUP-02.2: Ambiguous-owner items that might belong to the person are not included in their draft, but the output lists how many were left out and why.
- **R-FUP-03. Recipient** comes from the roster email. Missing email → the draft is still created with `To` empty, and the output flags `NO RECIPIENT: add email to people.json`.
- **R-FUP-04. Re-running updates, not duplicates.** The store keeps the draft id per owner; a second run calls `update_draft` for that id (if still present), else creates a new one.
  - AC-FUP-04.1: Two runs → one draft, content refreshed.
- **R-FUP-05. Gmail adapter is injectable.** Real adapter and a fake for tests. `--dry-run` prints the draft (to/subject/body) and writes nothing to Gmail.
  - AC-FUP-05.1: Connector unavailable or draft call fails → clear error, exit 1, store unchanged; suggest `--dry-run`.
  - AC-FUP-05.2: Tests never touch the real Gmail connector.
- **R-FUP-06. Draft content is polite plain text, in the user's voice template** (`.claude/skills/followup-drafting`), with no invented facts: only fields from the store.

### 4.10 Storage and reporting (R-STO, R-RPT)

- **R-STO-01.** Store is a single JSON file `.actiontrack/store.json` (override `--store`), written atomically; includes a `schema_version`.
  - AC-STO-01.1: A crash mid-write never leaves a corrupt store (temp file + rename).
  - AC-STO-01.2: A corrupt or unknown-version store → error with guidance, never overwritten silently.
- **R-RPT-01. Every command exits 0 on success, 1 on error, 2 on usage/ambiguity**, with human-readable messages on stderr, data on stdout.

### 4.11 Non-functional (R-NFR)

- **R-NFR-01.** Ingesting the 36 sample files takes under 2 seconds on a normal laptop.
- **R-NFR-02.** Deterministic: same inputs and `--today` give byte-identical output.
- **R-NFR-03.** Test suite: `python -m pytest -q`, line coverage ≥ 85% on the package; every test names the AC IDs it covers.

## 5. Acceptance examples (end to end on `samples/notes/`)

- **AE1.** `ingest samples/notes` → 32 ingested, 4 skipped (empty, binary, no header, .txt) with reasons, 1 `ACTION:` line reported unsupported, quoted/code/comment checkboxes excluded, no crash.
- **AE2.** `list --owner "Priya Nair" --status open --today 2026-10-01` → merged revised-quote item is not shown (done); footer reports ambiguous-Priya items excluded.
- **AE3.** `list --owner Priya` → exit 2 with candidates.
- **AE4.** `done <id>` for the "Meera to ask Acme for procurement contact" item, then `list --status open` no longer shows it.
- **AE5.** `followup "Karan Joshi" --dry-run` → draft with Karan's open items grouped by meeting, overdue marked, plus `NO RECIPIENT` if the roster has no email.
- **AE6.** `followup "Karan Joshi"` with the fake Gmail adapter → exactly one `create_draft` call, zero send calls.

## 6. Open questions (need your decision)

- [ ] **OQ-1. How does the CLI reach the Gmail MCP connector?** A standalone Python process cannot call the connector that Claude Code holds. Recommended: the CLI builds the draft (`to`, `subject`, `body` JSON) and a thin adapter hands it to a headless `claude -p` call restricted to `create_draft`/`update_draft` (allowedTools), with `--dry-run` and a file-based adapter as fallbacks. Alternative: CLI only writes draft JSON, and Claude Code (this session) calls `create_draft`. Which do you want?
- [ ] **OQ-2. Wrong merges.** Is a similarity-based merge acceptable, or should you confirm every non-exact merge interactively?
- [ ] **OQ-3. Date fallback.** Filename-date fallback (R-ING-04, `2026-10-03-sales-pipeline.md`) is a documented exception to "never guess dates". Accept, or skip such notes?
- [ ] **OQ-4. Manual `assign <id> <full name>`** to resolve ambiguous owners without editing notes: add to scope?
- [ ] **OQ-5. Checkboxes outside `## Action items`** in the offsite note (Morning/Afternoon sections): track them (current spec) or only the formal section?
- [ ] **OQ-6. "Everyone" items** (e.g. "Everyone to submit Q4 goals"): list-only (current), or fan out to every attendee in follow-ups?
- [ ] **OQ-7. `people.json` emails.** You need to supply the roster (names + emails); I will not invent addresses. Sample roster to be added with placeholder `@example.com` addresses for tests only.
