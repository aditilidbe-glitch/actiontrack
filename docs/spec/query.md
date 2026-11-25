# Module spec: List, done and assign

Part of the actiontrack spec. Index and shared context: [../spec.md](../spec.md).
Requirement IDs and wording are unchanged from the original single-file spec.

- **Source:** `src/actiontrack/query.py`
- **Tests:** `tests/test_query.py`
- **Requirements:** R-LST-01, R-LST-02, R-DON-01, R-OWN-05
- **Acceptance criteria:** 15

## Requirements

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

- **R-DON-01. `actiontrack done <id>`** marks the item done with a timestamp and marks it manual.
  - AC-DON-01.1: Item becomes `done`; listing with `--status open` no longer shows it; re-ingest keeps it done.
  - AC-DON-01.2: Unknown id → error, exit 1. Already done → message, exit 0, no change.
  - AC-DON-01.3: IDs are short, stable (`AT-xxxxxx`), and unique; a unique prefix is accepted; an ambiguous prefix is rejected with candidates.

- **R-OWN-05. `actiontrack assign <id> <full name>`** resolves an ambiguous owner to one known person, persistently.
  - AC-OWN-05.1: `assign <id> "Priya Nair"` on an item whose owner is `Priya?` (candidates Nair, Shah) makes the owner Priya Nair; the original ambiguous owner is kept as `assigned_from`; note files are never modified.
  - AC-OWN-05.2: Short or ambiguous names (`Priya`), `everyone`, `unassigned`, unknown people, items with no ambiguous owner that can be that person, and unknown ids are rejected (exit 2 or 1) and change nothing.
  - AC-OWN-05.3: Re-ingest keeps the assignment; a later ambiguous mention of the same short name merges into the assigned item.
  - AC-OWN-05.4: Assigning twice is a no-op with a message and exit 0.
