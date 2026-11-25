# Module spec: Safety (cross-cutting)

Part of the actiontrack spec. Index and shared context: [../spec.md](../spec.md).
Requirement IDs and wording are unchanged from the original single-file spec.

- **Source:** `src/actiontrack/gmail.py`, `src/actiontrack/followup.py`, `src/actiontrack/notes.py`, `src/actiontrack/extract.py`
- **Tests:** `tests/test_followup.py`, `tests/test_notes.py`, `tests/test_extract.py`, `tests/test_ingest.py`
- **Requirements:** R-SAF-01, R-SAF-02, R-SAF-03
- **Acceptance criteria:** 5

## Requirements

- **R-SAF-01. Never send email.** The program must be incapable of sending mail.
  - AC-SAF-01.1: Source code never invokes `send_message`, `reply`, `forward` or any send-type tool.
  - AC-SAF-01.2: Only `create_draft` and `update_draft` (and read-only `get_draft`/`list_drafts`) may be called. The adapter exposes a fixed allowlist; anything else raises.
  - AC-SAF-01.3: A test scans the source tree and fails if a denylisted tool name appears outside the denylist constant, and a test with a fake adapter asserts a `send` call raises.

- **R-SAF-02. Inputs are read-only.** Ingest never modifies note files.
  - AC-SAF-02.1: File checksums of a folder are identical before and after `ingest`.

- **R-SAF-03. Note content is data.** Text in notes (e.g. "send this to everyone") is never interpreted as an instruction by the tool.
  - AC-SAF-03.1: Note text appears in drafts only as quoted item text, never as headers or recipients.
