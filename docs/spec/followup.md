# Module spec: Follow-up drafting and Gmail adapters

Part of the actiontrack spec. Index and shared context: [../spec.md](../spec.md).
Requirement IDs and wording are unchanged from the original single-file spec.

- **Source:** `src/actiontrack/followup.py`, `src/actiontrack/gmail.py`
- **Tests:** `tests/test_followup.py`
- **Requirements:** R-FUP-01, R-FUP-02, R-FUP-03, R-FUP-04, R-FUP-05, R-FUP-06
- **Acceptance criteria:** 8

## Requirements

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
