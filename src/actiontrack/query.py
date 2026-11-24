"""List filtering, owner-name handling and `done` (spec R-LST-01/02, R-DON-01, R-DAT-03)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from datetime import date, datetime

from actiontrack.dates import STATUS_DONE, STATUS_OPEN, STATUS_OVERDUE, compute_status
from actiontrack.models import ActionTrackError, Item, Owner, OwnerKind, Person
from actiontrack.owners import EVERYONE_LABEL, UNASSIGNED_LABEL, owner_display
from actiontrack.store import Store, resolve_id

VALID_STATUSES = (STATUS_OPEN, STATUS_DONE, STATUS_OVERDUE)
OWNER_UNASSIGNED_QUERY = "unassigned"
OWNER_EVERYONE_QUERY = "everyone"


class UsageError(ActionTrackError):
    """Invalid arguments (exit code 2)."""


class AmbiguousOwnerError(UsageError):
    """A short owner name matches several people (exit code 2)."""

    def __init__(self, query: str, candidates: list[str]) -> None:
        names = ", ".join(candidates)
        super().__init__(f"'{query}' is ambiguous: {names}. Use a full name.")
        self.candidates = candidates


class OwnerNotFoundError(ActionTrackError):
    """No known person matches the owner query (exit code 1)."""


@dataclass(frozen=True)
class ListFilters:
    owner: str | None = None
    status: str | None = None
    due_before: date | None = None


@dataclass(frozen=True)
class ViewItem:
    item: Item
    status: str


@dataclass
class ListResult:
    items: list[ViewItem] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class OwnerTarget:
    """A resolved --owner query: a full name or a special group."""

    kind: OwnerKind
    name: str


def known_people(store: Store, roster: Sequence[Person]) -> list[str]:
    """Every full name seen in the store or roster."""
    names: dict[str, str] = {p.name.lower(): p.name for p in roster}
    for item in store.items.values():
        for owner in item.owners:
            if owner.kind is OwnerKind.RESOLVED:
                names.setdefault(owner.name.lower(), owner.name)
            for candidate in owner.candidates:
                names.setdefault(candidate.lower(), candidate)
    return sorted(names.values())


def resolve_owner_query(store: Store, roster: Sequence[Person], query: str) -> OwnerTarget:
    """Resolve an --owner / followup argument without guessing (R-LST-02)."""
    lowered = query.strip().lower()
    if lowered == OWNER_UNASSIGNED_QUERY:
        return OwnerTarget(OwnerKind.UNASSIGNED, UNASSIGNED_LABEL)
    if lowered == OWNER_EVERYONE_QUERY:
        return OwnerTarget(OwnerKind.EVERYONE, EVERYONE_LABEL)
    people = known_people(store, roster)
    exact = [p for p in people if p.lower() == lowered]
    if exact:
        return OwnerTarget(OwnerKind.RESOLVED, exact[0])
    by_first = [p for p in people if p.split()[0].lower() == lowered]
    if len(by_first) == 1:
        return OwnerTarget(OwnerKind.RESOLVED, by_first[0])
    if len(by_first) > 1:
        raise AmbiguousOwnerError(query, by_first)
    raise OwnerNotFoundError(f"no known owner matches '{query}'")


def owned_by(item: Item, target: OwnerTarget) -> bool:
    if target.kind is OwnerKind.RESOLVED:
        return any(o.kind is OwnerKind.RESOLVED and o.name == target.name for o in item.owners)
    return any(o.kind is target.kind for o in item.owners)


def ambiguous_for(item: Item, target: OwnerTarget) -> bool:
    """True when the item has an ambiguous owner that could be `target`."""
    return target.kind is OwnerKind.RESOLVED and any(
        o.kind is OwnerKind.AMBIGUOUS and target.name in o.candidates for o in item.owners
    )


def validate_status(status: str | None) -> None:
    if status is not None and status not in VALID_STATUSES:
        raise UsageError(f"invalid status '{status}'; choose one of: {', '.join(VALID_STATUSES)}")


def parse_iso_date(text: str, label: str) -> date:
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise UsageError(f"invalid {label} '{text}'; expected YYYY-MM-DD") from exc


def _sort_key(view: ViewItem) -> tuple[bool, str, str, str]:
    owner = owner_display(view.item.owners[0]).lower() if view.item.owners else ""
    return (view.item.due is None, view.item.due or "", owner, view.item.id)


def list_items(
    store: Store, roster: Sequence[Person], filters: ListFilters, today: date
) -> ListResult:
    """Filter and sort items (AND of all filters), with explanatory notes."""
    validate_status(filters.status)
    target = resolve_owner_query(store, roster, filters.owner) if filters.owner else None
    result = ListResult()
    excluded_ambiguous = 0
    excluded_no_due = 0
    for item in store.items.values():
        if target is not None and not owned_by(item, target):
            excluded_ambiguous += int(ambiguous_for(item, target) and not item.done)
            continue
        status = compute_status(item.done, item.due, today)
        if filters.status and status != filters.status:
            continue
        if filters.due_before is not None:
            if item.due is None:
                excluded_no_due += 1
                continue
            if date.fromisoformat(item.due) >= filters.due_before:
                continue
        result.items.append(ViewItem(item, status))
    result.items.sort(key=_sort_key)
    _add_notes(result, target, excluded_ambiguous, excluded_no_due)
    return result


def _add_notes(result: ListResult, target: OwnerTarget | None, ambiguous: int, no_due: int) -> None:
    if ambiguous and target is not None:
        result.notes.append(
            f"{ambiguous} item(s) with an ambiguous owner that may be {target.name} are not included"
        )
    if no_due:
        result.notes.append(f"{no_due} item(s) with no due date were excluded by --due-before")


@dataclass(frozen=True)
class AssignResult:
    item: Item
    changed: bool


def _assignable(owner: Owner, name: str) -> bool:
    """An ambiguous owner can become `name` if it lists no candidates or lists that name."""
    return owner.kind is OwnerKind.AMBIGUOUS and (not owner.candidates or name in owner.candidates)


def assign_owner(store: Store, roster: Sequence[Person], id_text: str, owner_name: str) -> AssignResult:
    """Resolve an ambiguous owner to one known person (R-OWN-05). Never touches note files."""
    target = resolve_owner_query(store, roster, owner_name)
    if target.kind is not OwnerKind.RESOLVED:
        raise UsageError("assign needs the full name of a single person")
    item_id = resolve_id(store, id_text)
    item = store.items[item_id]
    if any(o.kind is OwnerKind.RESOLVED and o.name == target.name for o in item.owners) and item.assigned_from:
        return AssignResult(item, False)
    if not any(_assignable(o, target.name) for o in item.owners):
        raise UsageError(f"{item_id} has no ambiguous owner that can be {target.name}")
    owners = tuple(
        Owner(OwnerKind.RESOLVED, target.name) if _assignable(o, target.name) else o for o in item.owners
    )
    updated = replace(item, owners=owners, assigned_from=item.assigned_from or item.owners)
    store.items[item_id] = updated
    return AssignResult(updated, True)


@dataclass(frozen=True)
class DoneResult:
    item: Item
    changed: bool


def mark_done(store: Store, id_text: str, now: datetime) -> DoneResult:
    """Mark an item done manually (R-DON-01). Already-done items are unchanged."""
    item_id = resolve_id(store, id_text)
    item = store.items[item_id]
    if item.done:
        return DoneResult(item, False)
    updated = replace(item, done=True, manual_done=True, done_at=now.isoformat(timespec="seconds"))
    store.items[item_id] = updated
    return DoneResult(updated, True)
