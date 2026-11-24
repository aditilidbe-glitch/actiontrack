"""U10 tests: CLI and end-to-end on the real samples. Covers R-RPT-01, R-NFR-01..03, AE1..AE6."""

from __future__ import annotations

import hashlib
import io
import json
import time
from pathlib import Path

import pytest

from actiontrack.cli import main
from actiontrack.gmail import FakeDraftAdapter
from actiontrack.models import EXIT_ERROR, EXIT_OK, EXIT_USAGE

ROSTER = Path(__file__).resolve().parent.parent / "samples" / "people.example.json"


class Runner:
    def __init__(self, tmp_path: Path, samples: Path) -> None:
        self.store = tmp_path / "store.json"
        self.samples = samples
        self.fake = FakeDraftAdapter()

    def run(self, *args: str, roster: bool = True) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        argv = [*args, "--store", str(self.store), "--today", "2026-10-20"]
        if roster:
            argv += ["--people", str(ROSTER)]
        code = main(argv, out, err, adapter_factory=lambda: self.fake)
        return code, out.getvalue(), err.getvalue()


@pytest.fixture
def cli(tmp_path: Path, samples_copy: Path) -> Runner:
    runner = Runner(tmp_path, samples_copy)
    code, _, _ = runner.run("ingest", str(samples_copy))
    assert code == EXIT_OK
    return runner


def test_ae1_ingest_summary(tmp_path: Path, samples_copy: Path) -> None:
    runner = Runner(tmp_path, samples_copy)
    code, out, _ = runner.run("ingest", str(samples_copy))
    assert code == EXIT_OK
    assert "files seen: 36" in out and "ingested: 32" in out and "skipped: 4" in out
    assert "empty file" in out and "not valid UTF-8 text" in out and "unsupported format: ACTION:" in out
    assert "meeting date taken from filename" in out


def test_ae2_list_owner_status(cli: Runner) -> None:
    code, out, err = cli.run("list", "--owner", "Priya Nair", "--status", "open")
    assert code == EXIT_OK
    assert "send the revised quote" not in out
    assert "ambiguous owner" in err


def test_ae3_ambiguous_owner_exits_2(cli: Runner) -> None:
    code, _, err = cli.run("list", "--owner", "Priya")
    assert code == EXIT_USAGE
    assert "Priya Nair" in err and "Priya Shah" in err


def test_ae4_done_then_list(cli: Runner) -> None:
    _, out, _ = cli.run("list", "--json", "--owner", "Meera Iyer")
    item = next(i for i in json.loads(out) if "ask Acme for their procurement contact" in i["text"])
    assert cli.run("done", item["id"])[0] == EXIT_OK
    _, after, _ = cli.run("list", "--json", "--status", "open")
    assert item["id"] not in {i["id"] for i in json.loads(after)}
    assert "already done" in cli.run("done", item["id"])[1]


def test_ae5_dry_run_followup(cli: Runner) -> None:
    code, out, _ = cli.run("followup", "Karan Joshi", "--dry-run")
    assert code == EXIT_OK
    assert "DRY RUN" in out and "To: karan.joshi@example.com" in out and "(OVERDUE)" in out
    assert cli.fake.calls == []


def test_ae5_missing_email_is_flagged(cli: Runner, tmp_path: Path) -> None:
    roster = tmp_path / "r.json"
    roster.write_text(json.dumps({"people": [{"name": "Karan Joshi"}]}), encoding="utf-8")
    out, err = io.StringIO(), io.StringIO()
    code = main(["followup", "Karan Joshi", "--dry-run", "--store", str(cli.store), "--people", str(roster), "--today", "2026-10-20"], out, err)
    assert code == EXIT_OK and "NO RECIPIENT" in out.getvalue()


def test_ae6_followup_creates_one_draft_no_send(cli: Runner) -> None:
    code, out, _ = cli.run("followup", "Karan Joshi")
    assert code == EXIT_OK
    assert "not sent" in out
    assert [c[0] for c in cli.fake.calls] == ["create_draft"]


def test_followup_ambiguous_creates_nothing(cli: Runner) -> None:
    code, _, _ = cli.run("followup", "Priya")
    assert code == EXIT_USAGE and cli.fake.calls == []


def test_gmail_failure_exits_1(cli: Runner) -> None:
    cli.fake.fail = True
    code, _, err = cli.run("followup", "Karan Joshi")
    assert code == EXIT_ERROR and "error:" in err


def test_missing_folder_exits_1_and_store_untouched(tmp_path: Path, samples_copy: Path) -> None:
    runner = Runner(tmp_path, samples_copy)
    code, _, err = runner.run("ingest", str(tmp_path / "nope"))
    assert code == EXIT_ERROR and "folder not found" in err and not runner.store.exists()


def test_usage_errors_exit_2(cli: Runner) -> None:
    assert cli.run("list", "--status", "bogus")[0] == EXIT_USAGE
    assert cli.run("list", "--due-before", "2026-13-40")[0] == EXIT_USAGE
    assert main(["frobnicate"], io.StringIO(), io.StringIO()) == EXIT_USAGE


def test_unknown_owner_and_id_exit_1(cli: Runner) -> None:
    assert cli.run("list", "--owner", "Zed")[0] == EXIT_ERROR
    assert cli.run("done", "AT-zzzzzz")[0] == EXIT_ERROR


def test_bad_roster_exits_1(cli: Runner, tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("{nope", encoding="utf-8")
    out, err = io.StringIO(), io.StringIO()
    code = main(["list", "--store", str(cli.store), "--people", str(bad)], out, err)
    assert code == EXIT_ERROR


def test_json_output_parses_and_is_deterministic(cli: Runner) -> None:
    first = cli.run("list", "--json")[1]
    assert isinstance(json.loads(first), list)
    assert cli.run("list", "--json")[1] == first
    assert cli.run("list")[1] == cli.run("list")[1]


def test_today_env_var_and_flag(cli: Runner, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ACTIONTRACK_TODAY", "2026-09-01")
    out, err = io.StringIO(), io.StringIO()
    main(["list", "--status", "overdue", "--store", str(cli.store), "--people", str(ROSTER)], out, err)
    assert "0 item(s)" in out.getvalue()


def test_missing_default_roster_warns(cli: Runner, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    out, err = io.StringIO(), io.StringIO()
    code = main(["list", "--store", str(cli.store), "--today", "2026-10-20"], out, err)
    assert code == EXIT_OK and "no roster file" in err.getvalue()


def test_samples_unchanged_after_full_run(tmp_path: Path, samples_dir: Path) -> None:
    """AC-SAF-02.1 on the real read-only corpus."""
    def digest() -> dict[str, str]:
        return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in samples_dir.iterdir()}

    before = digest()
    runner = Runner(tmp_path, samples_dir)
    runner.run("ingest", str(samples_dir))
    runner.run("followup", "Karan Joshi")
    assert digest() == before


def test_ingest_is_fast(tmp_path: Path, samples_copy: Path) -> None:
    """R-NFR-01."""
    runner = Runner(tmp_path, samples_copy)
    start = time.perf_counter()
    runner.run("ingest", str(samples_copy))
    assert time.perf_counter() - start < 2.0


def test_ingest_twice_cli_reports_zero_new(cli: Runner, samples_copy: Path) -> None:
    _, out, _ = cli.run("ingest", str(samples_copy))
    assert "items: 0 new, 0 updated, 0 merged" in out


def test_assign_command(cli: Runner) -> None:
    _, out, _ = cli.run("list", "--json")
    item = next(i for i in json.loads(out) if "sign off the cutover checklist" in i["text"])
    assert cli.run("assign", item["id"], "Priya")[0] == EXIT_USAGE
    assert cli.run("assign", item["id"], "Priya Nair")[0] == EXIT_OK
    assert "already assigned" in cli.run("assign", item["id"], "Priya Nair")[1]
    _, after, _ = cli.run("list", "--json", "--owner", "Priya Nair")
    assert item["id"] in {i["id"] for i in json.loads(after)}
    assert cli.run("assign", "AT-zzzzzz", "Priya Nair")[0] == EXIT_ERROR
