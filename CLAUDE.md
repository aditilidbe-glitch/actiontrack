# actiontrack

A Python CLI that ingests markdown meeting notes, tracks action items, and **drafts (never sends)** Gmail follow-ups through the Gmail MCP connector.

Commands: `ingest <folder>`, `list` (`--owner`, `--status open|done|overdue`, `--due-before`), `done <id>`, `followup <owner>`.

## Hard rules

1. **NEVER send email.** Only the Gmail connector's `create_draft` / `update_draft` / `get_draft` / `list_drafts` may be used. Never call `send_message`, `reply`, `forward`, or any tool that delivers mail, in code, tests, scripts, or interactively. The app code must not even reference those tool names except in a denylist test that asserts they are never called.
2. **No code before the spec is approved.** `docs/spec.md` must be approved by the user in chat first.
3. `samples/notes/` is a read-only copy of the sample notes. Never edit those files; tests use them as fixtures. The original folder (`Downloads\notes`) is never modified.
4. Malformed or non-note input is skipped and reported, never crashes ingest and never silently disappears.
5. Never guess an owner or date. Missing or ambiguous values are stored as unknown/ambiguous and surfaced.
6. No secrets or personal data in commits. Do not commit `.remember/`.
7. Ask the user instead of assuming when a decision is theirs.

## Spec-driven development workflow

1. Brainstorm to `docs/spec.md` (index and context) with per-module requirements in `docs/spec/*.md` (requirement IDs like `R-ING-01`, acceptance criteria like `AC-ING-01.1`). STOP for user approval.
2. Plan to `docs/plans/` (units `U1..Un`, test scenarios per unit, each traced to requirement IDs).
3. Project skills in `.claude/skills/` (note parsing, follow-up drafting).
4. Implement unit by unit, test first, run against `samples/notes/`.
5. Commit atomically (smart-commit), referencing spec IDs in messages; README; open PR.

Every test and commit references the spec IDs it covers. Spec changes go through the user.

## Stack

- Python 3.11+ (dev machine has 3.14), stdlib `argparse`, `pytest` for tests.
- Storage: local file under `.actiontrack/` (format decided in the spec).
- Gmail: Gmail MCP connector behind an adapter interface so tests use a fake.

## Test command

```
python -m pytest -q
```

## Skills to use (`/coditas:...`)

- `coditas:brainstorm` for the spec
- `coditas:plan` for `docs/plans/`
- `coditas:code-gen` when writing source
- `coditas:test-coverage` after every source edit
- `coditas:smart-commit` (smart-commit) for commits
- `coditas:create-pr` / `pr-description` for the PR
- Project skills: `.claude/skills/note-parsing`, `.claude/skills/followup-drafting`
