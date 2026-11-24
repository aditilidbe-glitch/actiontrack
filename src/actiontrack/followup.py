"""Follow-up draft composition and orchestration (spec R-FUP-01..06).

Drafts only. The body uses only fields from the store (R-FUP-06); template as
defined in .claude/skills/followup-drafting.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import date

from actiontrack.dates import STATUS_OVERDUE, compute_status
from actiontrack.gmail import DraftAdapter, DraftPayload, GmailError
from actiontrack.models import Item, OwnerKind, Person, Source
from actiontrack.query import UsageError, ambiguous_for, owned_by, resolve_owner_query
from actiontrack.roster import find_person
from actiontrack.store import Store

SENDER_PLACEHOLDER = "<your name>"
ACTION_CREATED = "created"
ACTION_UPDATED = "updated"
ACTION_DRY_RUN = "dry-run"
ACTION_NONE = "none"
SUBJECT_PLURAL = "Follow-up: {count} open action items"
SUBJECT_SINGULAR = "Follow-up: 1 open action item"
OVERDUE_MARK = " (OVERDUE)"
NO_DUE_TEXT = "no due date"


@dataclass
class FollowupResult:
    owner: str
    action: str
    payload: DraftPayload | None = None
    draft_id: str | None = None
    item_count: int = 0
    no_recipient: bool = False
    excluded_ambiguous: int = 0
    notes: list[str] = field(default_factory=list)


def latest_source(item: Item) -> Source:
    return max(item.sources, key=lambda s: (s.meeting_date, s.file, s.line))


def _due_text(item: Item, today: date) -> str:
    if item.due is None:
        return NO_DUE_TEXT if not item.due_raw else f"due {item.due_raw} (date unclear)"
    mark = OVERDUE_MARK if compute_status(item.done, item.due, today) == STATUS_OVERDUE else ""
    return f"due {item.due}{mark}"


def _group_by_meeting(items: Sequence[Item]) -> list[tuple[Source, list[Item]]]:
    groups: dict[tuple[str, str, str], list[Item]] = defaultdict(list)
    sources: dict[tuple[str, str, str], Source] = {}
    for item in items:
        source = latest_source(item)
        key = (source.meeting_date, source.meeting_title, source.file)
        groups[key].append(item)
        sources[key] = source
    ordered = sorted(groups)
    return [(sources[k], sorted(groups[k], key=lambda i: (i.due is None, i.due or "", i.id))) for k in ordered]


def compose_body(owner_name: str, items: Sequence[Item], today: date, sender: str = SENDER_PLACEHOLDER) -> str:
    """Plain-text body per the followup-drafting template."""
    lines = [f"Hi {owner_name.split()[0]},", "", "Here is a quick recap of the action items currently open for you.", ""]
    for source, group in _group_by_meeting(items):
        lines.append(f"{source.meeting_title} ({source.meeting_date}, {source.file})")
        lines.extend(f"- {item.text}, {_due_text(item, today)}" for item in group)
        lines.append("")
    lines.append("If any of these are done or need a new date, just reply and let me know.")
    lines.extend(["", "Thanks,", sender])
    return "\n".join(lines) + "\n"


def compose_subject(count: int) -> str:
    return SUBJECT_SINGULAR if count == 1 else SUBJECT_PLURAL.format(count=count)


def run_followup(
    store: Store,
    roster: Sequence[Person],
    owner_query: str,
    adapter: DraftAdapter | None,
    today: date,
    dry_run: bool = False,
    sender: str = SENDER_PLACEHOLDER,
) -> FollowupResult:
    """Create or update one Gmail draft for `owner_query` (never sends)."""
    target = resolve_owner_query(store, roster, owner_query)
    if target.kind is not OwnerKind.RESOLVED:
        raise UsageError(f"cannot draft a follow-up for {target.name}: it is not a single person")
    open_items = [i for i in store.items.values() if owned_by(i, target) and not i.done]
    excluded = sum(1 for i in store.items.values() if ambiguous_for(i, target) and not i.done)
    result = FollowupResult(owner=target.name, action=ACTION_NONE, excluded_ambiguous=excluded)
    if not open_items:
        return result
    person = find_person(list(roster), target.name)
    email = person.email if person and person.email else ""
    payload = DraftPayload(email, compose_subject(len(open_items)), compose_body(target.name, open_items, today, sender))
    result.payload, result.item_count, result.no_recipient = payload, len(open_items), not email
    if dry_run:
        result.action = ACTION_DRY_RUN
        return result
    if adapter is None:
        raise GmailError("no Gmail adapter configured; use --dry-run")
    _send_to_adapter(store, adapter, target.name, payload, result)
    return result


def _send_to_adapter(
    store: Store, adapter: DraftAdapter, owner: str, payload: DraftPayload, result: FollowupResult
) -> None:
    key = owner.lower()
    existing = store.drafts.get(key)
    if existing:
        try:
            result.draft_id = adapter.update_draft(existing, payload)
            result.action = ACTION_UPDATED
        except GmailError:
            result.notes.append(f"previous draft {existing} could not be updated; created a new one")
    if result.draft_id is None:
        result.draft_id = adapter.create_draft(payload)
        result.action = ACTION_CREATED
    store.drafts[key] = result.draft_id
