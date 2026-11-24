"""Shared factories for tests."""

from __future__ import annotations

from actiontrack.models import Item, Owner, OwnerKind, Source


def make_source(**overrides: object) -> Source:
    fields: dict[str, object] = {
        "file": "2026-09-01-quote-portal-kickoff.md",
        "line": 12,
        "meeting_title": "Quote portal kickoff",
        "meeting_date": "2026-09-01",
        "checked": False,
        "raw_text": "Priya to send the revised quote to Acme by Friday",
        "due_phrase": "Friday",
    }
    fields.update(overrides)
    return Source(**fields)  # type: ignore[arg-type]


def make_item(**overrides: object) -> Item:
    fields: dict[str, object] = {
        "id": "AT-a1b2c3",
        "text": "send the revised quote to Acme by Friday",
        "owners": (Owner(kind=OwnerKind.RESOLVED, name="Priya Nair"),),
        "collaborators": (),
        "due": "2026-09-04",
        "due_raw": "Friday",
        "due_vague": False,
        "done": False,
        "manual_done": False,
        "done_at": None,
        "sources": (make_source(),),
    }
    fields.update(overrides)
    return Item(**fields)  # type: ignore[arg-type]


def find_item(store, text_fragment: str, owner: str | None = None) -> Item:
    """Find the single item whose text contains `text_fragment` (and owner name)."""
    matches = [
        i
        for i in store.items.values()
        if text_fragment.lower() in i.text.lower()
        and (owner is None or any(o.name == owner for o in i.owners))
    ]
    assert len(matches) == 1, f"{text_fragment!r}/{owner}: {len(matches)} matches"
    return matches[0]
