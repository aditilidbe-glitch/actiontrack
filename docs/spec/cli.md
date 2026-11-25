# Module spec: CLI, reporting and non-functional

Part of the actiontrack spec. Index and shared context: [../spec.md](../spec.md).
Requirement IDs and wording are unchanged from the original single-file spec.

- **Source:** `src/actiontrack/cli.py`, `src/actiontrack/__main__.py`
- **Tests:** `tests/test_cli.py`
- **Requirements:** R-RPT-01, R-NFR-01, R-NFR-02, R-NFR-03
- **Acceptance criteria:** 0

## Requirements

- **R-RPT-01. Every command exits 0 on success, 1 on error, 2 on usage/ambiguity**, with human-readable messages on stderr, data on stdout.

- **R-NFR-01.** Ingesting the 36 sample files takes under 2 seconds on a normal laptop.

- **R-NFR-02.** Deterministic: same inputs and `--today` give byte-identical output.

- **R-NFR-03.** Test suite: `python -m pytest -q`, line coverage ≥ 85% on the package; every test names the AC IDs it covers.
