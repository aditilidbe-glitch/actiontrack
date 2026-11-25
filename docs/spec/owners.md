# Module spec: Owners, roster and same-first-name resolution

Part of the actiontrack spec. Index and shared context: [../spec.md](../spec.md).
Requirement IDs and wording are unchanged from the original single-file spec.

- **Source:** `src/actiontrack/owners.py`, `src/actiontrack/roster.py`
- **Tests:** `tests/test_owners.py`
- **Requirements:** R-OWN-01, R-OWN-02, R-OWN-03, R-OWN-04
- **Acceptance criteria:** 15

## Requirements

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
