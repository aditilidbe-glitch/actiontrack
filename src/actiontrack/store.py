"""JSON store with atomic writes and stable short IDs (spec R-STO-01, R-DON-01.3, R-FUP-04)."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from actiontrack.models import SCHEMA_VERSION, ActionTrackError, Item, ModelError

DEFAULT_STORE_RELPATH = Path(".actiontrack") / "store.json"
ID_PREFIX = "AT-"
ID_MIN_HEX = 6
ID_MAX_HEX = 40


class StoreError(ActionTrackError):
    """Raised for unreadable, corrupt or incompatible stores. Never overwrites."""


class UnknownIdError(StoreError):
    """No item matches the given id or prefix."""


class AmbiguousIdError(StoreError):
    """A prefix matches more than one item."""

    def __init__(self, prefix: str, candidates: list[str]) -> None:
        super().__init__(f"id prefix '{prefix}' is ambiguous: {', '.join(candidates)}")
        self.candidates = candidates


@dataclass
class Store:
    """In-memory view of the store file."""

    items: dict[str, Item] = field(default_factory=dict)
    drafts: dict[str, str] = field(default_factory=dict)  # owner key -> draft id
    notes: dict[str, str] = field(default_factory=dict)  # note file -> sha256

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "items": {item_id: item.to_dict() for item_id, item in sorted(self.items.items())},
            "drafts": dict(sorted(self.drafts.items())),
            "notes": dict(sorted(self.notes.items())),
        }


def load_store(path: Path) -> Store:
    """Load the store; a missing file is an empty store. Corrupt data raises StoreError."""
    if not path.exists():
        return Store()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise StoreError(f"cannot read store {path}: {exc.strerror or exc}") from exc
    except json.JSONDecodeError as exc:
        raise StoreError(f"store {path} is not valid JSON ({exc}); it was left untouched") from exc
    return _from_dict(data, path)


def _from_dict(data: object, path: Path) -> Store:
    if not isinstance(data, dict):
        raise StoreError(f"store {path} has an unexpected structure; it was left untouched")
    version = data.get("schema_version")
    if version != SCHEMA_VERSION:
        raise StoreError(
            f"store {path} has schema_version {version!r}, expected {SCHEMA_VERSION}; "
            "it was left untouched"
        )
    try:
        items = {k: Item.from_dict(v) for k, v in data.get("items", {}).items()}
    except (ModelError, AttributeError) as exc:
        raise StoreError(f"store {path} is corrupt: {exc}; it was left untouched") from exc
    return Store(
        items=items,
        drafts=dict(data.get("drafts", {})),
        notes=dict(data.get("notes", {})),
    )


def save_store(path: Path, store: Store) -> None:
    """Write atomically: temp file in the same directory, then rename."""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp_path = path.with_name(path.name + ".tmp")
        temp_path.write_text(json.dumps(store.to_dict(), indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        os.replace(temp_path, path)
    except OSError as exc:
        raise StoreError(f"cannot write store {path}: {exc.strerror or exc}") from exc


def allocate_id(existing: Iterable[str], seed: str) -> str:
    """Deterministic short id from `seed`; lengthens the hash on collision."""
    taken = set(existing)
    digest = hashlib.sha1(seed.encode("utf-8")).hexdigest()
    for length in range(ID_MIN_HEX, ID_MAX_HEX + 1):
        candidate = ID_PREFIX + digest[:length]
        if candidate not in taken:
            return candidate
    raise StoreError(f"could not allocate a unique id for seed {seed!r}")


def resolve_id(store: Store, text: str) -> str:
    """Resolve an exact id or unique prefix (with or without 'AT-')."""
    wanted = text.strip().lower()
    if not wanted.startswith(ID_PREFIX.lower()):
        wanted = ID_PREFIX.lower() + wanted
    matches = sorted(i for i in store.items if i.lower().startswith(wanted))
    exact = [i for i in matches if i.lower() == wanted]
    if exact:
        return exact[0]
    if not matches:
        raise UnknownIdError(f"no item with id '{text}'")
    if len(matches) > 1:
        raise AmbiguousIdError(text, matches)
    return matches[0]
