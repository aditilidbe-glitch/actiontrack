"""U5 tests: owners and roster. Covers R-OWN-01..04."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from actiontrack.models import OwnerKind, Person
from actiontrack.owners import (
    EVERYONE_LABEL,
    UNASSIGNED_LABEL,
    owner_display,
    owner_key,
    parse_owner_text,
    resolve_name,
    resolve_owners,
)
from actiontrack.roster import RosterError, find_person, load_roster

ROSTER = [
    Person("Priya Nair", "priya.nair@example.com", ("Priya N.",)),
    Person("Priya Shah", None, ("Priya S.",)),
    Person("Rahul Mehta"),
    Person("Rahul Verma"),
    Person("Anita Desai"),
    Person("Sam Okafor"),
]


def test_parse_basic_owner_and_task() -> None:
    spec = parse_owner_text("Priya to send the revised quote to Acme by Friday")
    assert spec.names == ("Priya",)
    assert spec.task == "send the revised quote to Acme by Friday"


def test_parse_at_mention() -> None:
    """AC-OWN-01.1."""
    spec = parse_owner_text("@anita: audit colour contrast on the dashboard by Mon")
    assert spec.names == ("anita",)
    assert spec.task.startswith("audit colour contrast")


def test_parse_joint_owners() -> None:
    """AC-OWN-01.2."""
    assert parse_owner_text("Anita & Rahul to agree on the component API").names == ("Anita", "Rahul")


def test_parse_collaborator() -> None:
    """AC-OWN-01.3."""
    spec = parse_owner_text("Lena (with Priya) to collect user feedback")
    assert spec.names == ("Lena",)
    assert spec.collaborators == ("Priya",)


def test_parse_initial_owner() -> None:
    assert parse_owner_text("Priya N. to send revised quote").names == ("Priya N.",)


@pytest.mark.parametrize("text", ["Send the quote soon", "", "Reminder: the quote is late"])
def test_parse_without_owner_gives_warning(text: str) -> None:
    spec = parse_owner_text(text)
    assert spec.names == ()
    assert spec.warning


@pytest.mark.parametrize(
    ("raw", "kind", "label"),
    [("Someone", OwnerKind.UNASSIGNED, UNASSIGNED_LABEL), ("TBD", OwnerKind.UNASSIGNED, UNASSIGNED_LABEL),
     ("Everyone", OwnerKind.EVERYONE, EVERYONE_LABEL), ("Team", OwnerKind.EVERYONE, EVERYONE_LABEL)],
)
def test_special_owners(raw: str, kind: OwnerKind, label: str) -> None:
    """AC-OWN-02.1/02.2."""
    owner = resolve_name(raw, [], [])
    assert (owner.kind, owner.name) == (kind, label)


def test_single_attending_first_name_resolves() -> None:
    """AC-OWN-03.1."""
    owner = resolve_name("Priya", ["Priya Nair", "Rahul Mehta"], ROSTER)
    assert (owner.kind, owner.name) == (OwnerKind.RESOLVED, "Priya Nair")


def test_two_same_first_names_are_ambiguous() -> None:
    """AC-OWN-03.3 / 03.4."""
    owner = resolve_name("Priya", ["Priya Nair", "Priya Shah", "Sam Okafor"], ROSTER)
    assert owner.kind is OwnerKind.AMBIGUOUS
    assert owner.candidates == ("Priya Nair", "Priya Shah")
    assert owner_display(owner) == "Priya?"


def test_initial_disambiguates() -> None:
    """AC-OWN-03.5."""
    attendees = ["Priya Nair", "Priya Shah"]
    assert resolve_name("Priya S.", attendees, ROSTER).name == "Priya Shah"
    assert resolve_name("Priya N.", attendees, ROSTER).name == "Priya Nair"


def test_no_attendees_falls_back_to_roster() -> None:
    """AC-OWN-03.7."""
    assert resolve_name("Sam", [], ROSTER).name == "Sam Okafor"
    assert resolve_name("Rahul", [], ROSTER).kind is OwnerKind.AMBIGUOUS
    assert resolve_name("Rahul", [], [Person("Rahul Mehta")]).name == "Rahul Mehta"


def test_unknown_first_name_is_ambiguous_with_no_candidates() -> None:
    owner = resolve_name("Zoe", ["Priya Nair"], ROSTER)
    assert owner.kind is OwnerKind.AMBIGUOUS and owner.candidates == ()


def test_full_name_and_case_insensitive() -> None:
    assert resolve_name("anita desai", ["Anita Desai"], []).name == "Anita Desai"
    assert resolve_name("ANITA", ["Anita Desai"], []).name == "Anita Desai"


def test_alias_resolves() -> None:
    assert resolve_name("Priya N.", [], ROSTER).name == "Priya Nair"


def test_resolve_owners_unassigned_when_no_names() -> None:
    owners, collaborators = resolve_owners(parse_owner_text("no owner here"), [], ROSTER)
    assert owners[0].kind is OwnerKind.UNASSIGNED and collaborators == ()


def test_owner_keys_differ_for_ambiguous_vs_resolved() -> None:
    amb = resolve_name("Priya", ["Priya Nair", "Priya Shah"], [])
    res = resolve_name("Priya", ["Priya Nair"], [])
    assert owner_key(amb) != owner_key(res)


def test_load_roster_ok_and_lookup(tmp_path: Path) -> None:
    path = tmp_path / "people.json"
    path.write_text(json.dumps({"people": [{"name": "Karan Joshi", "email": "k@example.com"}]}), encoding="utf-8")
    people = load_roster(path)
    assert find_person(people, "karan joshi").email == "k@example.com"  # type: ignore[union-attr]
    assert find_person(people, "Nobody") is None


@pytest.mark.parametrize(
    "content",
    ["{not json", '{"people": "x"}', '{"people": [{"email": "a@b.c"}]}',
     '{"people": [{"name": "A B"}, {"name": "a b"}]}', '{"people": [{"name": "A B", "email": "nope"}]}'],
)
def test_bad_roster_raises_with_path(tmp_path: Path, content: str) -> None:
    """AC-OWN-04.2."""
    path = tmp_path / "people.json"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(RosterError, match="people.json"):
        load_roster(path)


def test_missing_roster_raises(tmp_path: Path) -> None:
    with pytest.raises(RosterError):
        load_roster(tmp_path / "absent.json")
