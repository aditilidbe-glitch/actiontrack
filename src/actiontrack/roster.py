"""Roster file loading (spec R-OWN-04).

Format: {"people": [{"name": "Priya Nair", "email": "...", "aliases": ["Priya N."]}]}
A bare JSON list of people is also accepted.
"""

from __future__ import annotations

import json
from pathlib import Path

from actiontrack.models import ActionTrackError, ModelError, Person

DEFAULT_ROSTER_NAME = "people.json"


class RosterError(ActionTrackError):
    """Raised when the roster file is unreadable or invalid."""


def load_roster(path: Path) -> list[Person]:
    """Load and validate the roster; raises RosterError with the file path."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise RosterError(f"cannot read roster {path}: {exc.strerror or exc}") from exc
    except json.JSONDecodeError as exc:
        raise RosterError(f"roster {path} is not valid JSON: {exc}") from exc
    entries = data.get("people") if isinstance(data, dict) else data
    if not isinstance(entries, list):
        raise RosterError(f"roster {path}: expected a list of people")
    people = [_parse_person(entry, path) for entry in entries]
    _reject_duplicates(people, path)
    return people


def _parse_person(entry: object, path: Path) -> Person:
    try:
        person = Person.from_dict(entry)  # type: ignore[arg-type]
    except ModelError as exc:
        raise RosterError(f"roster {path}: {exc}") from exc
    if person.email is not None and "@" not in person.email:
        raise RosterError(f"roster {path}: invalid email for {person.name}")
    return person


def _reject_duplicates(people: list[Person], path: Path) -> None:
    seen: set[str] = set()
    for person in people:
        key = person.name.lower()
        if key in seen:
            raise RosterError(f"roster {path}: duplicate person '{person.name}'")
        seen.add(key)


def find_person(people: list[Person], name: str) -> Person | None:
    """Case-insensitive lookup by full name."""
    lowered = name.lower()
    return next((p for p in people if p.name.lower() == lowered), None)
