# actiontrack

A small Python CLI that ingests markdown meeting notes, tracks the action items in them, and **drafts (never sends)** Gmail follow-ups per owner.

- Spec: [docs/spec.md](docs/spec.md) (requirement IDs and acceptance criteria)
- Plan: [docs/plans/2026-11-24-001-feat-actiontrack-plan.md](docs/plans/2026-11-24-001-feat-actiontrack-plan.md)
- Project rules: [CLAUDE.md](CLAUDE.md)

## Hard rule: it never sends email

The only Gmail tools the program may call are `create_draft`, `update_draft` (and read-only `get_draft`/`list_drafts`). Sending tools are denylisted in `src/actiontrack/gmail.py`, the adapter raises if anything else is requested, and a test scans the source tree to make sure no send-type tool name appears anywhere. You review each draft in Gmail and send it yourself.

## Install

Requires Python 3.11+. No runtime dependencies.

```powershell
python -m venv .venv
.venv\Scripts\python -m pip install -e ".[dev]"
```

## Commands

```text
actiontrack ingest <folder> [--recursive]
actiontrack list [--owner NAME] [--status open|done|overdue] [--due-before YYYY-MM-DD] [--json]
actiontrack done <id>
actiontrack assign <id> "<full name>"
actiontrack followup <owner> [--dry-run]
```

Common options on every command: `--store PATH` (default `.actiontrack/store.json`), `--people PATH` (default `./people.json` if present), `--today YYYY-MM-DD` (or env `ACTIONTRACK_TODAY`, for reproducible runs).

Exit codes: `0` ok, `1` error, `2` usage error or ambiguous name. Data goes to stdout, messages to stderr.

Try it on the bundled samples:

```powershell
.venv\Scripts\python -m actiontrack ingest samples/notes --people samples/people.example.json
.venv\Scripts\python -m actiontrack list --status overdue --today 2026-10-20 --people samples/people.example.json
.venv\Scripts\python -m actiontrack followup "Karan Joshi" --dry-run --people samples/people.example.json
```

## What it handles

| Situation | Behaviour |
|---|---|
| Same action in several meetings | Merged into one item (same owner, similar text). Latest status wins, latest due date wins, all sources kept, merges are reported. |
| Missing owner (`Someone`, `TBD`) or group (`Everyone`, `Team`) | Stored as `(unassigned)` / `(everyone)`. Listed, never followed up. |
| Missing or vague due date | Stored as no due date, never "overdue". Vague phrases like "mid-October" are kept as raw text. |
| Same first name (two Priyas, two Rahuls) | Resolved from the meeting's attendees and `people.json`. If still unclear the owner is stored as ambiguous (`Priya?`); `list --owner Priya` and `followup Priya` refuse and list the candidates. It never guesses. Fix one with `assign <id> "Priya Nair"` (persistent, notes untouched). |
| Malformed notes (empty, binary, no header, no date) | Skipped and reported with a reason. Other notes still ingest. |
| Quoted lines, code fences, HTML comments | Checkboxes inside them are excluded and counted. |
| Nested bullets, `*`/`+` markers, tables with Owner / Action / Due | Parsed as items. |
| `ACTION:` lines | Reported as unsupported, not tracked. |

Notes are never modified. Re-ingesting is idempotent, and a manual `done` is never undone by a later ingest.

## Roster (`people.json`)

```json
{"people": [{"name": "Priya Nair", "email": "priya.nair@example.com", "aliases": ["Priya N."]}]}
```

Emails come only from this file. `people.json` is git-ignored so real addresses are never committed; copy `samples/people.example.json` and edit it. If an owner has no email the draft is still created with an empty To field and flagged `NO RECIPIENT`. `samples/people.example.json` uses placeholder `@example.com` addresses.

## Gmail drafts

`followup` builds one draft per owner (open and overdue items grouped by meeting) and hands it to an adapter:

- **Default**: a headless `claude -p` call restricted with `--allowedTools` to the Gmail draft tools. Set `ACTIONTRACK_GMAIL_TOOL_PREFIX` to the tool-name prefix of your Gmail connector (default `mcp__claude_ai_Gmail__`). This path has **not** been exercised against real Gmail yet. Verify with `--dry-run` first, then one real draft.
- **`--dry-run`**: prints the draft and makes no Gmail call.

Re-running `followup` for the same owner updates the existing draft instead of creating another.

## Tests

```powershell
.venv\Scripts\python -m pytest -q
.venv\Scripts\python -m pytest -q --cov=actiontrack --cov-report=term-missing
```

The suite runs against the real sample notes in `samples/notes/` (a read-only copy of the originals) with a fake Gmail adapter. Tests never contact Gmail; a fixture blocks real subprocess calls.

## Layout

```text
src/actiontrack/
  dates.py      due-date resolution          notes.py     note reading and headers
  extract.py    action-item extraction       owners.py    owners and name resolution
  roster.py     people.json                  merge.py     duplicate detection
  ingest.py     ingest orchestration         store.py     JSON store, atomic writes, ids
  query.py      list filters and done        followup.py  draft composition
  gmail.py      draft-only adapters          cli.py       commands and exit codes
.claude/skills/ note-parsing, followup-drafting (project skills)
docs/           spec and plans
samples/        sample notes and example roster
```

## Decisions

Resolved with the project owner: similarity-based merging is kept with every merge reported (OQ-2), the filename-date fallback stays with a warning (OQ-3), `assign` exists (OQ-4), all checkboxes except under "Parking lot" are tracked (OQ-5), "Everyone" items are list-only (OQ-6), and the real roster stays local (OQ-7). See section 6 of the spec.
