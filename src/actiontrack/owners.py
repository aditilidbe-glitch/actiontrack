"""Owner extraction and same-first-name resolution (spec R-OWN-01..03).

Never guesses: a short name resolves only when exactly one candidate exists.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass

from actiontrack.models import Owner, OwnerKind, Person

UNASSIGNED_LABEL = "(unassigned)"
EVERYONE_LABEL = "(everyone)"
MAX_OWNER_WORDS = 6

_EVERYONE_WORDS = {"everyone", "everybody", "team", "all", "we"}
_UNASSIGNED_WORDS = {"someone", "somebody", "tbd", "tba", "nobody", "unassigned", "?"}
_AT_PREFIX_RE = re.compile(r"^@(?P<name>[\w.-]+)\s*:?\s*(?P<rest>.*)$")
_TO_SPLIT_RE = re.compile(r"^(?P<names>.+?)\s+to\s+(?P<rest>\S.*)$", re.IGNORECASE)
_WITH_RE = re.compile(r"\(\s*with\s+(?P<names>[^)]+)\)", re.IGNORECASE)
_NAME_SPLIT_RE = re.compile(r"\s*(?:&|,|\band\b)\s*", re.IGNORECASE)
_INITIAL_RE = re.compile(r"^[A-Za-z]\.?$")


@dataclass(frozen=True)
class OwnerSpec:
    """Raw owner names found in item text, plus the remaining task text."""

    names: tuple[str, ...]
    collaborators: tuple[str, ...]
    task: str
    warning: str | None = None


def parse_owner_text(text: str) -> OwnerSpec:
    """Split item text into owner names, collaborators and the task."""
    stripped = text.strip()
    if at_match := _AT_PREFIX_RE.match(stripped):
        return OwnerSpec((at_match.group("name"),), (), at_match.group("rest").strip())
    collaborators: tuple[str, ...] = ()
    head = stripped
    to_match = _TO_SPLIT_RE.match(head)
    if not to_match:
        return OwnerSpec((), (), stripped, "no owner found")
    names_part = to_match.group("names")
    if with_match := _WITH_RE.search(names_part):
        collaborators = _split_names(with_match.group("names"))
        names_part = _WITH_RE.sub("", names_part).strip()
    if not _looks_like_names(names_part):
        return OwnerSpec((), (), stripped, "no owner found")
    return OwnerSpec(_split_names(names_part), collaborators, to_match.group("rest").strip())


def _split_names(part: str) -> tuple[str, ...]:
    return tuple(n.strip() for n in _NAME_SPLIT_RE.split(part) if n.strip())


def _looks_like_names(part: str) -> bool:
    words = part.split()
    return 0 < len(words) <= MAX_OWNER_WORDS and (part[0].isupper() or part[0] == "@")


def _known_people(attendees: Sequence[str], roster: Sequence[Person]) -> list[str]:
    """Full names from roster and attendees, de-duplicated case-insensitively."""
    seen: dict[str, str] = {}
    for name in [p.name for p in roster] + list(attendees):
        seen.setdefault(name.lower(), name)
    return list(seen.values())


def _alias_lookup(roster: Sequence[Person]) -> dict[str, str]:
    return {alias.lower(): person.name for person in roster for alias in person.aliases}


def resolve_name(raw: str, attendees: Sequence[str], roster: Sequence[Person]) -> Owner:
    """Resolve one raw name to an Owner (resolved / ambiguous / unassigned / everyone)."""
    name = raw.strip()
    lowered = name.lower().rstrip(".")
    if lowered in _EVERYONE_WORDS:
        return Owner(OwnerKind.EVERYONE, EVERYONE_LABEL)
    if lowered in _UNASSIGNED_WORDS:
        return Owner(OwnerKind.UNASSIGNED, UNASSIGNED_LABEL)
    alias_hit = _alias_lookup(roster).get(name.lower())
    if alias_hit:
        return Owner(OwnerKind.RESOLVED, alias_hit)
    return _resolve_person(name, attendees, roster)


def _resolve_person(name: str, attendees: Sequence[str], roster: Sequence[Person]) -> Owner:
    tokens = name.split()
    pool = _known_people(attendees, roster)
    exact = next((p for p in pool if p.lower() == name.lower()), None)
    if exact:
        return Owner(OwnerKind.RESOLVED, exact)
    initial = tokens[1].rstrip(".").lower() if len(tokens) == 2 and _INITIAL_RE.match(tokens[1]) else None
    if len(tokens) >= 2 and initial is None:
        return Owner(OwnerKind.RESOLVED, name)
    scope = list(attendees) if attendees else [p.name for p in roster]
    first = tokens[0].lower().lstrip("@")
    candidates = sorted({p for p in scope if _matches(p, first, initial)})
    if len(candidates) == 1:
        return Owner(OwnerKind.RESOLVED, candidates[0])
    return Owner(OwnerKind.AMBIGUOUS, name, tuple(candidates))


def _matches(full_name: str, first: str, initial: str | None) -> bool:
    parts = full_name.split()
    if not parts or parts[0].lower() != first:
        return False
    return initial is None or (len(parts) > 1 and parts[-1].lower().startswith(initial))


def owner_key(owner: Owner) -> str:
    """Stable key used for matching/merging (R-DUP-01)."""
    if owner.kind is OwnerKind.RESOLVED:
        return owner.name.lower()
    if owner.kind is OwnerKind.AMBIGUOUS:
        return f"ambiguous:{owner.name.lower()}"
    return owner.kind.value


def owner_display(owner: Owner) -> str:
    """Human-readable owner label for tables and drafts."""
    if owner.kind is OwnerKind.AMBIGUOUS:
        return f"{owner.name}?"
    return owner.name


def resolve_owners(
    spec: OwnerSpec, attendees: Sequence[str], roster: Sequence[Person]
) -> tuple[tuple[Owner, ...], tuple[str, ...]]:
    """Resolve all names in a spec; no names means one unassigned owner."""
    if not spec.names:
        return (Owner(OwnerKind.UNASSIGNED, UNASSIGNED_LABEL),), _collaborator_names(spec, attendees, roster)
    owners = tuple(resolve_name(n, attendees, roster) for n in spec.names)
    return owners, _collaborator_names(spec, attendees, roster)


def _collaborator_names(
    spec: OwnerSpec, attendees: Sequence[str], roster: Sequence[Person]
) -> tuple[str, ...]:
    resolved = (resolve_name(n, attendees, roster) for n in spec.collaborators)
    return tuple(o.name for o in resolved)
