"""U1 tests: domain models. Covers R-STO-01, R-RPT-01, R-DAT-02."""

from __future__ import annotations

import dataclasses

import pytest

from actiontrack import models
from actiontrack.models import (
    EXIT_ERROR,
    EXIT_OK,
    EXIT_USAGE,
    SCHEMA_VERSION,
    Item,
    ModelError,
    Owner,
    OwnerKind,
    Person,
    Source,
)


def make_source(**overrides: object) -> Source:
    fields: dict[str, object] = {
        "file": "2026-09-01-quote-portal-kickoff.md",
        "line": 12,
        "meeting_title": "Quote portal kickoff",
        "meeting_date": "2026-09-01",
        "checked": False,
        "raw_text": "Priya to send the revised quote to Acme by Friday",
    }
    fields.update(overrides)
    return Source(**fields)  # type: ignore[arg-type]


def make_item(**overrides: object) -> Item:
    fields: dict[str, object] = {
        "id": "AT-a1b2c3",
        "text": "Priya to send the revised quote to Acme by Friday",
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


def test_constants_are_stable() -> None:
    """R-STO-01 schema version, R-RPT-01 exit-code constants."""
    assert SCHEMA_VERSION == 1
    assert (EXIT_OK, EXIT_ERROR, EXIT_USAGE) == (0, 1, 2)


def test_item_round_trips_with_two_sources() -> None:
    """R-STO-01: happy path round trip."""
    item = make_item(
        done=True,
        sources=(make_source(), make_source(file="2026-09-08-quote-portal-weekly.md", line=9, checked=True)),
    )
    assert Item.from_dict(item.to_dict()) == item


def test_item_with_unknown_due_and_ambiguous_owner_round_trips() -> None:
    """R-DAT-02, R-OWN-03: due is None, vague flag and candidates survive."""
    owner = Owner(
        kind=OwnerKind.AMBIGUOUS,
        name="Priya",
        candidates=("Priya Nair", "Priya Shah"),
    )
    item = make_item(owners=(owner,), due=None, due_raw="mid-October", due_vague=True)
    restored = Item.from_dict(item.to_dict())
    assert restored == item
    assert restored.due is None
    assert restored.due_vague is True
    assert restored.owners[0].candidates == ("Priya Nair", "Priya Shah")


def test_unassigned_and_everyone_owners_round_trip() -> None:
    """R-OWN-02 kinds are preserved."""
    for kind in (OwnerKind.UNASSIGNED, OwnerKind.EVERYONE):
        item = make_item(owners=(Owner(kind=kind, name=kind.value),))
        assert Item.from_dict(item.to_dict()).owners[0].kind is kind


def test_models_are_immutable() -> None:
    """R-STO-01: frozen dataclasses cannot be mutated in place."""
    item = make_item()
    with pytest.raises(dataclasses.FrozenInstanceError):
        item.done = True  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        item.sources[0].line = 99  # type: ignore[misc]


def test_person_round_trips_with_aliases() -> None:
    person = Person(name="Priya Nair", email="priya.nair@example.com", aliases=("Priya N.",))
    assert Person.from_dict(person.to_dict()) == person


def test_person_email_is_optional() -> None:
    person = Person.from_dict({"name": "Karan Joshi"})
    assert person.email is None
    assert person.aliases == ()


@pytest.mark.parametrize("missing", ["id", "text", "owners", "sources", "done"])
def test_item_from_dict_missing_field_raises_model_error(missing: str) -> None:
    """R-STO-01: a clear domain error, not KeyError."""
    data = make_item().to_dict()
    del data[missing]
    with pytest.raises(ModelError, match=missing):
        Item.from_dict(data)


def test_item_from_dict_rejects_unknown_owner_kind() -> None:
    data = make_item().to_dict()
    data["owners"][0]["kind"] = "nobody"
    with pytest.raises(ModelError, match="owner kind"):
        Item.from_dict(data)


def test_item_from_dict_rejects_non_mapping() -> None:
    with pytest.raises(ModelError):
        Item.from_dict("not a dict")  # type: ignore[arg-type]


def test_person_requires_name() -> None:
    with pytest.raises(ModelError, match="name"):
        Person.from_dict({"email": "x@example.com"})


@pytest.mark.parametrize("bad_name", ["", "   ", 42])
def test_person_rejects_blank_or_non_string_name(bad_name: object) -> None:
    with pytest.raises(ModelError, match="non-empty string"):
        Person.from_dict({"name": bad_name})


def test_model_error_is_an_actiontrack_error() -> None:
    assert issubclass(ModelError, models.ActionTrackError)


def test_assigned_from_round_trips_and_defaults_empty() -> None:
    """R-OWN-05."""
    original = (Owner(kind=OwnerKind.AMBIGUOUS, name="Priya", candidates=("Priya Nair", "Priya Shah")),)
    item = make_item(assigned_from=original)
    assert Item.from_dict(item.to_dict()).assigned_from == original
    data = make_item().to_dict()
    del data["assigned_from"]
    assert Item.from_dict(data).assigned_from == ()
