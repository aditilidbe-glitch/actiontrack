"""U6 tests: store. Covers R-STO-01, R-DON-01.3, R-FUP-04."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from helpers import make_item

from actiontrack.store import (
    AmbiguousIdError,
    Store,
    StoreError,
    UnknownIdError,
    allocate_id,
    load_store,
    resolve_id,
    save_store,
)


def test_save_then_load_round_trips(store_path: Path) -> None:
    store = Store(items={"AT-a1b2c3": make_item()}, drafts={"karan joshi": "d1"}, notes={"a.md": "abc"})
    save_store(store_path, store)
    loaded = load_store(store_path)
    assert loaded == store
    assert not store_path.with_name(store_path.name + ".tmp").exists()


def test_missing_file_is_empty_store(store_path: Path) -> None:
    assert load_store(store_path) == Store()


def test_custom_path_creates_parents(tmp_path: Path) -> None:
    deep = tmp_path / "a" / "b" / "store.json"
    save_store(deep, Store())
    assert deep.exists()


def test_failed_rename_keeps_old_file(store_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """AC-STO-01.1."""
    save_store(store_path, Store(drafts={"x": "1"}))
    before = store_path.read_text(encoding="utf-8")

    def boom(*args: object, **kwargs: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(StoreError):
        save_store(store_path, Store(drafts={"x": "2"}))
    assert store_path.read_text(encoding="utf-8") == before


@pytest.mark.parametrize("version", [0, 2, 99, "1"])
def test_unknown_or_newer_schema_is_refused_and_untouched(store_path: Path, version: object) -> None:
    """AC-STO-01.2."""
    store_path.parent.mkdir(parents=True)
    store_path.write_text(json.dumps({"schema_version": version, "items": {}}), encoding="utf-8")
    before = store_path.read_text(encoding="utf-8")
    with pytest.raises(StoreError, match="schema_version"):
        load_store(store_path)
    assert store_path.read_text(encoding="utf-8") == before


@pytest.mark.parametrize("content", ["{broken", "[]", '{"schema_version": 1, "items": {"x": {"id": "x"}}}'])
def test_corrupt_store_raises_and_is_untouched(store_path: Path, content: str) -> None:
    store_path.parent.mkdir(parents=True)
    store_path.write_text(content, encoding="utf-8")
    with pytest.raises(StoreError, match="untouched"):
        load_store(store_path)
    assert store_path.read_text(encoding="utf-8") == content


def test_ids_have_format_and_are_unique() -> None:
    taken: set[str] = set()
    for n in range(500):
        new_id = allocate_id(taken, f"seed-{n}")
        assert new_id.startswith("AT-") and len(new_id) == 9
        assert new_id not in taken
        taken.add(new_id)


def test_id_collision_lengthens_deterministically() -> None:
    first = allocate_id(set(), "same")
    second = allocate_id({first}, "same")
    assert second != first and second.startswith(first)
    assert allocate_id({first}, "same") == second


def test_resolve_id_exact_prefix_and_bare_hex() -> None:
    store = Store(items={"AT-a1b2c3": make_item(id="AT-a1b2c3"), "AT-a1ffff": make_item(id="AT-a1ffff")})
    assert resolve_id(store, "AT-a1b2c3") == "AT-a1b2c3"
    assert resolve_id(store, "a1b2") == "AT-a1b2c3"
    assert resolve_id(store, "AT-A1B2C3") == "AT-a1b2c3"


def test_resolve_id_errors() -> None:
    """AC-DON-01.3."""
    store = Store(items={"AT-a1b2c3": make_item(id="AT-a1b2c3"), "AT-a1ffff": make_item(id="AT-a1ffff")})
    with pytest.raises(AmbiguousIdError) as info:
        resolve_id(store, "a1")
    assert info.value.candidates == ["AT-a1b2c3", "AT-a1ffff"]
    with pytest.raises(UnknownIdError):
        resolve_id(store, "zzzz")


def test_draft_map_persists_and_can_be_replaced(store_path: Path) -> None:
    store = Store()
    store.drafts["karan joshi"] = "d1"
    save_store(store_path, store)
    reloaded = load_store(store_path)
    reloaded.drafts["karan joshi"] = "d2"
    del reloaded.drafts["karan joshi"]
    assert reloaded.drafts == {}
