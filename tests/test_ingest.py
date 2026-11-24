"""U7 tests: merge and ingest. Covers R-ING-01..03, R-DUP-01..03."""

from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

from helpers import find_item, make_item, make_source

from actiontrack.ingest import ingest_folder
from actiontrack.merge import SIMILARITY_THRESHOLD, find_best_match, similarity, task_tokens
from actiontrack.models import OwnerKind
from actiontrack.owners import owner_key
from actiontrack.query import mark_done
from actiontrack.store import Store

NOTE = """# Meeting: Weekly
Date: {date}
Attendees: Priya Nair, Sam Okafor

## Action items
{lines}
"""


def write_note(folder: Path, name: str, date: str, *lines: str) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_text(NOTE.format(date=date, lines="\n".join(lines)), encoding="utf-8")


def test_sample_corpus_counts_and_skips(ingested) -> None:
    """AC-ING-01.1, 01.2, AC-ING-03.1..03.5."""
    store, report = ingested
    assert (report.files_seen, report.ingested, len(report.skipped)) == (36, 32, 4)
    reasons = {s.file: s.reason for s in report.skipped}
    assert reasons["2026-09-09-notes-final-v2.md"] == "empty file"
    assert reasons["scratch.md"] == "not valid UTF-8 text"
    assert reasons["untitled.md"] == "no meeting header or date"
    assert reasons["2026-09-19-offsite-draft.txt"] == "not a markdown note"
    assert report.excluded == 3
    assert len(report.unsupported) == 1
    assert report.items_new == len(store.items)


def test_revised_quote_merges_to_one_done_item(ingested) -> None:
    """AC-DUP-01.1."""
    store, _ = ingested
    item = find_item(store, "revised quote to Acme", "Priya Nair")
    assert item.done is True
    assert [s.file for s in item.sources] == [
        "2026-09-01-quote-portal-kickoff.md", "2026-09-08-quote-portal-weekly.md", "2026-09-15-quote-portal-weekly.md",
    ]


def test_freeze_invoice_edits_has_two_sources(ingested) -> None:
    """AC-DUP-01.2."""
    store, _ = ingested
    assert len(find_item(store, "freeze invoice edits", "Karan Joshi").sources) == 2


def test_cloud_budget_is_done_with_three_sources(ingested) -> None:
    """AC-DUP-01.3."""
    store, _ = ingested
    item = find_item(store, "confirm cloud budget", "Sam Okafor")
    assert item.done and len(item.sources) == 3


def test_similar_but_different_items_are_not_merged(ingested) -> None:
    """AC-DUP-01.4."""
    store, _ = ingested
    assert find_item(store, "confirm cloud budget") is not find_item(store, "confirm rollback plan")


def test_wireframes_use_latest_due(ingested) -> None:
    """AC-DUP-02.1."""
    store, _ = ingested
    item = find_item(store, "share updated wireframes", "Anita Desai")
    assert item.due == "2026-09-24"
    assert len(item.sources) == 2


def test_ambiguous_owners_on_samples(ingested) -> None:
    """AC-OWN-03.3, 03.4, 03.6."""
    store, _ = ingested
    for fragment in ("sign off the cutover checklist", "review Anita's PR", "own the hiring plan", "architecture overview"):
        owner = find_item(store, fragment).owners[0]
        assert owner.kind is OwnerKind.AMBIGUOUS, fragment


def test_same_text_different_owners_never_merge(tmp_path: Path) -> None:
    """AC-DUP-01.5."""
    folder = tmp_path / "n"
    write_note(folder, "2026-09-01-a.md", "2026-09-01", "- [ ] Priya N. to send the deck by Friday")
    write_note(folder, "2026-09-02-b.md", "2026-09-02", "- [ ] Sam to send the deck by Friday")
    store = Store()
    ingest_folder(folder, store, [])
    assert len(store.items) == 2


def test_reingest_is_a_no_op(samples_dir: Path, roster) -> None:
    """AC-ING-02.1."""
    store = Store()
    ingest_folder(samples_dir, store, roster)
    snapshot = store.to_dict()["items"]
    second = ingest_folder(samples_dir, store, roster)
    assert store.to_dict()["items"] == snapshot
    assert (second.items_new, second.items_updated, second.merges) == (0, 0, [])


def test_manual_done_survives_reingest_with_note(tmp_path: Path) -> None:
    """AC-ING-02.2, AC-DUP-02.2."""
    folder = tmp_path / "n"
    write_note(folder, "2026-09-01-a.md", "2026-09-01", "- [ ] Sam to rotate the staging credentials")
    store = Store()
    ingest_folder(folder, store, [])
    (item,) = store.items.values()
    mark_done(store, item.id, datetime(2026, 9, 2, 10, 0))
    ingest_folder(folder, store, [])
    assert store.items[item.id].done is True
    write_note(folder, "2026-09-10-b.md", "2026-09-10", "- [ ] Sam to rotate the staging credentials")
    report = ingest_folder(folder, store, [])
    assert store.items[item.id].done is True
    assert any("marked done manually" in n for n in report.notes)


def test_checked_later_marks_done_and_changes_are_counted(tmp_path: Path) -> None:
    folder = tmp_path / "n"
    write_note(folder, "2026-09-01-a.md", "2026-09-01", "- [ ] Sam to rotate the staging credentials")
    store = Store()
    ingest_folder(folder, store, [])
    write_note(folder, "2026-09-01-a.md", "2026-09-01", "- [x] Sam to rotate the staging credentials")
    report = ingest_folder(folder, store, [])
    (item,) = store.items.values()
    assert item.done and report.items_updated == 1


def test_bad_file_does_not_stop_others(tmp_path: Path) -> None:
    """AC-ING-03.5."""
    folder = tmp_path / "n"
    write_note(folder, "2026-09-01-a.md", "2026-09-01", "- [ ] Sam to do a thing")
    (folder / "broken.md").write_bytes(b"\x00\x01\x02")
    store = Store()
    report = ingest_folder(folder, store, [])
    assert len(store.items) == 1 and len(report.skipped) == 1


def test_ingest_does_not_modify_samples(samples_copy: Path, roster) -> None:
    """AC-SAF-02.1."""
    before = {p.name: p.read_bytes() for p in samples_copy.iterdir()}
    ingest_folder(samples_copy, Store(), roster)
    assert {p.name: p.read_bytes() for p in samples_copy.iterdir()} == before


def test_empty_folder_ingests_nothing(tmp_path: Path) -> None:
    folder = tmp_path / "empty"
    folder.mkdir()
    store = Store()
    report = ingest_folder(folder, store, [])
    assert report.files_seen == 0 and not store.items


def test_recursive_flag(tmp_path: Path) -> None:
    folder = tmp_path / "n"
    write_note(folder / "sub", "2026-09-01-a.md", "2026-09-01", "- [ ] Sam to do a thing")
    assert not ingest_folder(folder, Store(), []).ingested
    assert ingest_folder(folder, Store(), [], recursive=True).ingested == 1


# --- similarity threshold boundary tests (plan U7) ---


def _item(tokens: str):
    return make_item(text=tokens, sources=(make_source(),))


def test_threshold_boundary_merges_at_threshold_not_below() -> None:
    owners = make_item().owners
    key = tuple(sorted(owner_key(o) for o in owners))
    base = _item("alpha beta gamma delta epsilon")
    at_threshold = task_tokens("alpha beta gamma")  # 3/5 == 0.6
    below = task_tokens("alpha beta gamma zeta eta theta")  # 3/8 < 0.6
    assert similarity(at_threshold, task_tokens(base.text)) == SIMILARITY_THRESHOLD
    assert find_best_match([base], key, at_threshold) is base
    assert find_best_match([base], key, below) is None


def test_named_sample_pairs_stay_on_the_right_side() -> None:
    must_merge = [
        ("set up staging by 2026-09-08", "set up the staging environment"),
        ("send revised quote to Acme by Friday", "send the revised quote to Acme"),
    ]
    must_not = [
        ("confirm cloud budget with finance", "confirm rollback plan by 2026-10-09"),
        ("review the schema mapping doc", "review the welcome email for accessibility"),
    ]
    for a, b in must_merge:
        assert similarity(task_tokens(a), task_tokens(b)) >= SIMILARITY_THRESHOLD, (a, b)
    for a, b in must_not:
        assert similarity(task_tokens(a), task_tokens(b)) < SIMILARITY_THRESHOLD, (a, b)


def test_samples_copy_is_a_real_copy(samples_copy: Path, samples_dir: Path) -> None:
    assert samples_copy != samples_dir
    shutil.rmtree(samples_copy)
    assert samples_dir.exists()
