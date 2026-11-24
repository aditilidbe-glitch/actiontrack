"""Domain models and shared constants.

Spec: R-STO-01 (schema), R-RPT-01 (exit codes), R-OWN-02/03 (owner kinds),
R-DAT-02 (unknown/vague due dates).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any

SCHEMA_VERSION = 1

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_USAGE = 2


class ActionTrackError(Exception):
    """Base class for all expected, user-reportable errors."""


class ModelError(ActionTrackError):
    """Raised when serialized data cannot be turned into a model."""


class OwnerKind(str, Enum):
    """How an item's owner was determined (R-OWN-02, R-OWN-03)."""

    RESOLVED = "resolved"
    AMBIGUOUS = "ambiguous"
    UNASSIGNED = "unassigned"
    EVERYONE = "everyone"


def _require(data: Mapping[str, Any], key: str, kind: str) -> Any:
    """Return data[key] or raise a ModelError naming the missing field."""
    if not isinstance(data, Mapping):
        raise ModelError(f"{kind}: expected an object, got {type(data).__name__}")
    if key not in data:
        raise ModelError(f"{kind}: missing required field '{key}'")
    return data[key]


@dataclass(frozen=True)
class Source:
    """One mention of an action item in one note."""

    file: str
    line: int
    meeting_title: str
    meeting_date: str
    checked: bool
    raw_text: str
    due_phrase: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "file": self.file,
            "line": self.line,
            "meeting_title": self.meeting_title,
            "meeting_date": self.meeting_date,
            "checked": self.checked,
            "raw_text": self.raw_text,
            "due_phrase": self.due_phrase,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Source:
        return cls(
            file=_require(data, "file", "source"),
            line=_require(data, "line", "source"),
            meeting_title=_require(data, "meeting_title", "source"),
            meeting_date=_require(data, "meeting_date", "source"),
            checked=_require(data, "checked", "source"),
            raw_text=_require(data, "raw_text", "source"),
            due_phrase=data.get("due_phrase"),
        )


@dataclass(frozen=True)
class Owner:
    """An owner of an item; `candidates` is only set for AMBIGUOUS owners."""

    kind: OwnerKind
    name: str
    candidates: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {"kind": self.kind.value, "name": self.name, "candidates": list(self.candidates)}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Owner:
        raw_kind = _require(data, "kind", "owner")
        try:
            kind = OwnerKind(raw_kind)
        except ValueError as exc:
            raise ModelError(f"owner kind '{raw_kind}' is not valid") from exc
        return cls(
            kind=kind,
            name=_require(data, "name", "owner"),
            candidates=tuple(data.get("candidates", ())),
        )


@dataclass(frozen=True)
class Person:
    """A roster entry (R-OWN-04)."""

    name: str
    email: str | None = None
    aliases: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "email": self.email, "aliases": list(self.aliases)}

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Person:
        name = _require(data, "name", "person")
        if not isinstance(name, str) or not name.strip():
            raise ModelError("person: 'name' must be a non-empty string")
        return cls(
            name=name,
            email=data.get("email"),
            aliases=tuple(data.get("aliases", ())),
        )


@dataclass(frozen=True)
class Item:
    """A tracked action item, possibly merged from several mentions (R-DUP)."""

    id: str
    text: str
    owners: tuple[Owner, ...]
    collaborators: tuple[str, ...]
    due: str | None
    due_raw: str | None
    due_vague: bool
    done: bool
    manual_done: bool
    done_at: str | None
    sources: tuple[Source, ...]
    assigned_from: tuple[Owner, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "assigned_from": [owner.to_dict() for owner in self.assigned_from],
            "id": self.id,
            "text": self.text,
            "owners": [owner.to_dict() for owner in self.owners],
            "collaborators": list(self.collaborators),
            "due": self.due,
            "due_raw": self.due_raw,
            "due_vague": self.due_vague,
            "done": self.done,
            "manual_done": self.manual_done,
            "done_at": self.done_at,
            "sources": [source.to_dict() for source in self.sources],
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Item:
        return cls(
            id=_require(data, "id", "item"),
            text=_require(data, "text", "item"),
            owners=tuple(Owner.from_dict(o) for o in _require(data, "owners", "item")),
            collaborators=tuple(data.get("collaborators", ())),
            due=data.get("due"),
            due_raw=data.get("due_raw"),
            due_vague=bool(data.get("due_vague", False)),
            done=_require(data, "done", "item"),
            manual_done=bool(data.get("manual_done", False)),
            done_at=data.get("done_at"),
            sources=tuple(Source.from_dict(s) for s in _require(data, "sources", "item")),
            assigned_from=tuple(Owner.from_dict(o) for o in data.get("assigned_from", ())),
        )
