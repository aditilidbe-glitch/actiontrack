"""Shared test helpers for actiontrack."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SAMPLES_DIR = REPO_ROOT / "samples" / "notes"


SAMPLE_ROSTER = REPO_ROOT / "samples" / "people.example.json"


@pytest.fixture(autouse=True)
def forbid_real_gmail(monkeypatch: pytest.MonkeyPatch) -> None:
    """R-FUP-05.2: tests never run a real subprocess for Gmail."""
    from actiontrack import gmail

    def _blocked(*args: object, **kwargs: object) -> None:
        raise AssertionError("tests must not run the real Gmail adapter")

    monkeypatch.setattr(gmail.subprocess, "run", _blocked)


@pytest.fixture
def roster():
    from actiontrack.roster import load_roster

    return load_roster(SAMPLE_ROSTER)


@pytest.fixture
def ingested(samples_dir: Path, roster):
    """A Store with the real sample corpus ingested, plus its report."""
    from actiontrack.ingest import ingest_folder
    from actiontrack.store import Store

    store = Store()
    report = ingest_folder(samples_dir, store, roster)
    return store, report


@pytest.fixture
def samples_dir() -> Path:
    """Read-only reference corpus (never modify)."""
    return SAMPLES_DIR


@pytest.fixture
def samples_copy(tmp_path: Path) -> Path:
    """A throwaway copy of the sample notes that tests may touch."""
    target = tmp_path / "notes"
    shutil.copytree(SAMPLES_DIR, target)
    return target


@pytest.fixture
def store_path(tmp_path: Path) -> Path:
    """Path for a temporary store file (not created yet)."""
    return tmp_path / ".actiontrack" / "store.json"
