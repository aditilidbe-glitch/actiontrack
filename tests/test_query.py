"""U8 tests: list filters, owner handling, done. Covers R-LST-01/02, R-DON-01, R-DAT-03."""

from __future__ import annotations

from datetime import date, datetime

import pytest
from helpers import find_item

from actiontrack.models import OwnerKind
from actiontrack.query import (
    AmbiguousOwnerError,
    ListFilters,
    OwnerNotFoundError,
    UsageError,
    list_items,
    mark_done,
    parse_iso_date,
    resolve_owner_query,
)
from actiontrack.store import AmbiguousIdError, UnknownIdError

TODAY = date(2026, 10, 20)


def listing(ingested, roster, **kwargs):
    store, _ = ingested
    return list_items(store, roster, ListFilters(**kwargs), TODAY)


def test_overdue_only_open_with_past_due(ingested, roster) -> None:
    """AC-LST-01.1."""
    result = listing(ingested, roster, status="overdue")
    assert result.items
    for view in result.items:
        assert not view.item.done and view.item.due is not None and view.item.due < TODAY.isoformat()


def test_done_and_open_statuses_partition(ingested, roster) -> None:
    store, _ = ingested
    counts = {s: len(listing(ingested, roster, status=s).items) for s in ("open", "done", "overdue")}
    assert sum(counts.values()) == len(store.items)


def test_owner_filter_with_ambiguity_footer(ingested, roster) -> None:
    """AC-LST-02.1."""
    result = listing(ingested, roster, owner="Priya Nair")
    assert result.items
    assert all(any(o.name == "Priya Nair" for o in v.item.owners) for v in result.items)
    assert any("ambiguous owner" in n for n in result.notes)


@pytest.mark.parametrize("name", ["Priya", "Rahul", "priya"])
def test_ambiguous_short_owner_is_rejected_with_candidates(ingested, roster, name: str) -> None:
    """AC-LST-02.2."""
    with pytest.raises(AmbiguousOwnerError) as info:
        listing(ingested, roster, owner=name)
    assert len(info.value.candidates) == 2
    assert isinstance(info.value, UsageError)


def test_unique_first_name_and_case_insensitive(ingested, roster) -> None:
    result = listing(ingested, roster, owner="karan")
    assert result.items and all(v.item.owners[0].name == "Karan Joshi" for v in result.items)


def test_special_owner_groups(ingested, roster) -> None:
    """AC-LST-02.3."""
    assert listing(ingested, roster, owner="Unassigned").items
    assert listing(ingested, roster, owner="everyone").items


def test_unknown_owner_raises_not_found(ingested, roster) -> None:
    """AC-LST-02.4."""
    with pytest.raises(OwnerNotFoundError):
        listing(ingested, roster, owner="Zed")


def test_due_before_is_strict_and_reports_null_due(ingested, roster) -> None:
    """AC-LST-01.2."""
    result = listing(ingested, roster, due_before=date(2026, 10, 2))
    assert result.items
    assert all(v.item.due is not None and v.item.due < "2026-10-02" for v in result.items)
    assert not any(v.item.due == "2026-10-02" for v in result.items)
    assert any("no due date" in n for n in result.notes)


def test_filters_combine_with_and(ingested, roster) -> None:
    result = listing(ingested, roster, owner="Karan Joshi", status="overdue", due_before=date(2026, 10, 10))
    assert result.items
    assert all(v.status == "overdue" and v.item.due < "2026-10-10" for v in result.items)


def test_invalid_status_and_date_are_usage_errors(ingested, roster) -> None:
    """AC-LST-01.3."""
    with pytest.raises(UsageError):
        listing(ingested, roster, status="bogus")
    with pytest.raises(UsageError):
        parse_iso_date("2026-13-01", "--due-before")


def test_sorted_by_due_nulls_last(ingested, roster) -> None:
    """AC-LST-01.4."""
    dues = [v.item.due for v in listing(ingested, roster).items]
    dated = [d for d in dues if d is not None]
    assert dated == sorted(dated)
    assert dues[: len(dated)] == dated and all(d is None for d in dues[len(dated):])


def test_joint_owner_item_appears_under_each_owner(ingested, roster) -> None:
    item = find_item(ingested[0], "agree on the component API")
    for owner in ("Anita Desai", "Rahul Mehta"):
        ids = {v.item.id for v in listing(ingested, roster, owner=owner).items}
        assert item.id in ids


def test_done_marks_item_and_persists_flag(ingested) -> None:
    """AC-DON-01.1."""
    store, _ = ingested
    item = find_item(store, "ask Acme for their procurement contact")
    result = mark_done(store, item.id, datetime(2026, 10, 1, 9, 0))
    assert result.changed and store.items[item.id].done and store.items[item.id].manual_done
    assert item.id not in {v.item.id for v in list_items(store, [], ListFilters(status="open"), TODAY).items}


def test_done_twice_and_unknown_and_ambiguous(ingested) -> None:
    """AC-DON-01.2, 01.3."""
    store, _ = ingested
    item = find_item(store, "ask Acme for their procurement contact")
    mark_done(store, item.id, datetime.now())
    assert mark_done(store, item.id, datetime.now()).changed is False
    with pytest.raises(UnknownIdError):
        mark_done(store, "AT-nope00", datetime.now())
    with pytest.raises(AmbiguousIdError):
        mark_done(store, "", datetime.now())


def test_resolve_owner_query_kinds(ingested, roster) -> None:
    store, _ = ingested
    assert resolve_owner_query(store, roster, "Karan Joshi").kind is OwnerKind.RESOLVED
    assert resolve_owner_query(store, roster, "everyone").kind is OwnerKind.EVERYONE


# --- assign (R-OWN-05) ---


def test_assign_resolves_ambiguous_owner_and_persists_original(ingested, roster) -> None:
    from actiontrack.query import assign_owner

    store, _ = ingested
    item = find_item(store, "sign off the cutover checklist")
    result = assign_owner(store, roster, item.id, "Priya Nair")
    assert result.changed
    updated = store.items[item.id]
    assert [(o.kind, o.name) for o in updated.owners] == [(OwnerKind.RESOLVED, "Priya Nair")]
    assert updated.assigned_from[0].kind is OwnerKind.AMBIGUOUS
    assert assign_owner(store, roster, item.id, "Priya Nair").changed is False


def test_assign_rejects_bad_targets(ingested, roster) -> None:
    from actiontrack.query import assign_owner

    store, _ = ingested
    ambiguous = find_item(store, "sign off the cutover checklist")
    resolved = find_item(store, "send the vendor invoice list")
    with pytest.raises(AmbiguousOwnerError):
        assign_owner(store, roster, ambiguous.id, "Priya")
    with pytest.raises(UsageError):
        assign_owner(store, roster, ambiguous.id, "everyone")
    with pytest.raises(UsageError, match="no ambiguous owner"):
        assign_owner(store, roster, ambiguous.id, "Sam Okafor")
    with pytest.raises(UsageError, match="no ambiguous owner"):
        assign_owner(store, roster, resolved.id, "Priya Nair")
    with pytest.raises(OwnerNotFoundError):
        assign_owner(store, roster, ambiguous.id, "Zed")
    with pytest.raises(UnknownIdError):
        assign_owner(store, roster, "AT-zzzzzz", "Priya Nair")


def test_assigned_item_is_listed_for_new_owner_and_survives_reingest(samples_dir, roster, ingested) -> None:
    from actiontrack.ingest import ingest_folder
    from actiontrack.query import assign_owner

    store, _ = ingested
    item = find_item(store, "sign off the cutover checklist")
    assign_owner(store, roster, item.id, "Priya Nair")
    report = ingest_folder(samples_dir, store, roster)
    assert (report.items_new, report.items_updated) == (0, 0)
    assert store.items[item.id].owners[0].name == "Priya Nair"
    ids = {v.item.id for v in list_items(store, roster, ListFilters(owner="Priya Nair"), TODAY).items}
    assert item.id in ids


def test_new_ambiguous_mention_merges_into_assigned_item(tmp_path, roster) -> None:
    from actiontrack.ingest import ingest_folder
    from actiontrack.query import assign_owner
    from actiontrack.store import Store

    folder = tmp_path / "n"
    folder.mkdir()
    template = "# Meeting: M\nDate: {d}\nAttendees: Priya Nair, Priya Shah\n\n## Action items\n- [{c}] Priya to sign off the checklist\n"
    (folder / "2026-09-01-a.md").write_text(template.format(d="2026-09-01", c=" "), encoding="utf-8")
    store = Store()
    ingest_folder(folder, store, roster)
    (item,) = store.items.values()
    assign_owner(store, roster, item.id, "Priya Shah")
    (folder / "2026-09-08-b.md").write_text(template.format(d="2026-09-08", c="x"), encoding="utf-8")
    ingest_folder(folder, store, roster)
    assert len(store.items) == 1
    (merged,) = store.items.values()
    assert merged.done and len(merged.sources) == 2 and merged.owners[0].name == "Priya Shah"
