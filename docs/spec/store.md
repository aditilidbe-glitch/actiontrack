# Module spec: Store and domain models

Part of the actiontrack spec. Index and shared context: [../spec.md](../spec.md).
Requirement IDs and wording are unchanged from the original single-file spec.

- **Source:** `src/actiontrack/store.py`, `src/actiontrack/models.py`
- **Tests:** `tests/test_store.py`, `tests/test_models.py`
- **Requirements:** R-STO-01
- **Acceptance criteria:** 2

## Requirements

- **R-STO-01.** Store is a single JSON file `.actiontrack/store.json` (override `--store`), written atomically; includes a `schema_version`.
  - AC-STO-01.1: A crash mid-write never leaves a corrupt store (temp file + rename).
  - AC-STO-01.2: A corrupt or unknown-version store → error with guidance, never overwritten silently.
