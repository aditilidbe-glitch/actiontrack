"""Ingest orchestration (spec R-ING-01..04, R-DUP-01..03, R-DON-01 persistence).

Idempotent: mentions are keyed by (file, raw text), so re-ingesting an
unchanged folder changes nothing and a manual `done` is never undone.
"""

from __future__ import annotations

import hashlib
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from datetime import date
from pathlib import Path

from actiontrack.dates import extract_due_phrase, resolve_due
from actiontrack.extract import KIND_TABLE, Finding, RawItem, extract_items
from actiontrack.merge import SIMILARITY_THRESHOLD, find_best_match, owners_key, task_tokens
from actiontrack.models import Item, Owner, Person, Source
from actiontrack.notes import Note, SkippedNote, discover, read_note
from actiontrack.owners import OwnerSpec, parse_owner_text, resolve_owners
from actiontrack.store import Store, allocate_id


@dataclass
class IngestReport:
    """Everything the CLI needs to print an ingest summary."""

    files_seen: int = 0
    ingested: int = 0
    skipped: list[SkippedNote] = field(default_factory=list)
    items_new: int = 0
    items_updated: int = 0
    merges: list[tuple[str, str, list[str]]] = field(default_factory=list)
    excluded: int = 0
    unsupported: list[tuple[str, Finding]] = field(default_factory=list)
    unrecognized: list[tuple[str, Finding]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Mention:
    """One interpreted action-item line from one note."""

    owners: tuple[Owner, ...]
    collaborators: tuple[str, ...]
    task: str
    source: Source


def ingest_folder(
    folder: Path,
    store: Store,
    roster: Sequence[Person],
    recursive: bool = False,
    threshold: float = SIMILARITY_THRESHOLD,
) -> IngestReport:
    """Ingest every note in `folder` into `store` (the caller saves the store)."""
    report = IngestReport()
    paths, skipped = discover(folder, recursive)
    report.files_seen = len(paths) + len(skipped)
    report.skipped.extend(skipped)
    notes = _read_notes(paths, folder, report)
    index = _source_index(store)
    for note in sorted(notes, key=lambda n: (n.meeting_date, n.file)):
        _ingest_note(note, store, roster, index, report, threshold)
        store.notes[note.file] = hashlib.sha256(note.path.read_bytes()).hexdigest()
    return report


def _read_notes(paths: list[Path], folder: Path, report: IngestReport) -> list[Note]:
    notes: list[Note] = []
    for path in paths:
        display = path.relative_to(folder).as_posix()
        result = read_note(path, display)
        if isinstance(result, SkippedNote):
            report.skipped.append(result)
            continue
        report.ingested += 1
        report.warnings.extend(f"{result.file}: {w}" for w in result.warnings)
        notes.append(result)
    return notes


def _source_index(store: Store) -> dict[tuple[str, str], str]:
    return {(s.file, s.raw_text): item.id for item in store.items.values() for s in item.sources}


def _ingest_note(
    note: Note,
    store: Store,
    roster: Sequence[Person],
    index: dict[tuple[str, str], str],
    report: IngestReport,
    threshold: float,
) -> None:
    result = extract_items(note.lines)
    report.excluded += len(result.excluded)
    report.unsupported.extend((note.file, f) for f in result.unsupported)
    report.unrecognized.extend((note.file, f) for f in result.unrecognized)
    for raw in result.items:
        mention = _build_mention(raw, note, roster, report)
        _apply_mention(mention, store, index, report, threshold)


def _build_mention(raw: RawItem, note: Note, roster: Sequence[Person], report: IngestReport) -> Mention:
    spec = _owner_spec(raw)
    if spec.warning:
        report.warnings.append(f"{note.file}:{raw.line}: {spec.warning}; item is unassigned")
    owners, collaborators = resolve_owners(spec, note.attendees, roster)
    phrase = raw.table_due or None
    if raw.kind != KIND_TABLE:
        found = extract_due_phrase(raw.text)
        phrase = found.text if found else None
    source = Source(
        file=note.file,
        line=raw.line,
        meeting_title=note.title,
        meeting_date=note.meeting_date.isoformat(),
        checked=raw.checked,
        raw_text=raw.text,
        due_phrase=phrase,
    )
    return Mention(owners, collaborators, spec.task, source)


def _owner_spec(raw: RawItem) -> OwnerSpec:
    if raw.kind == KIND_TABLE:
        names = parse_owner_text(f"{raw.table_owner} to x").names if raw.table_owner else ()
        return OwnerSpec(names, (), raw.text)
    return parse_owner_text(raw.text)


def _apply_mention(
    mention: Mention,
    store: Store,
    index: dict[tuple[str, str], str],
    report: IngestReport,
    threshold: float,
) -> None:
    key = (mention.source.file, mention.source.raw_text)
    if key in index:
        _refresh_source(store, index[key], mention, report)
        return
    match = find_best_match(
        store.items.values(), owners_key(mention.owners), task_tokens(mention.task), threshold
    )
    if match is None:
        _create_item(mention, store, index, report)
    else:
        _merge_into(match, mention, store, index, report)


def _create_item(mention: Mention, store: Store, index: dict[tuple[str, str], str], report: IngestReport) -> None:
    tokens = " ".join(sorted(task_tokens(mention.task)))
    seed = f"{'|'.join(owners_key(mention.owners))}|{tokens}"
    item = Item(
        id=allocate_id(store.items.keys(), seed),
        text=mention.task,
        owners=mention.owners,
        collaborators=mention.collaborators,
        due=None,
        due_raw=None,
        due_vague=False,
        done=False,
        manual_done=False,
        done_at=None,
        sources=(mention.source,),
    )
    store.items[item.id] = recompute(item)
    index[(mention.source.file, mention.source.raw_text)] = item.id
    report.items_new += 1


def _merge_into(
    existing: Item,
    mention: Mention,
    store: Store,
    index: dict[tuple[str, str], str],
    report: IngestReport,
) -> None:
    collaborators = tuple(dict.fromkeys(existing.collaborators + mention.collaborators))
    updated = recompute(replace(existing, collaborators=collaborators, sources=existing.sources + (mention.source,)))
    store.items[existing.id] = updated
    index[(mention.source.file, mention.source.raw_text)] = existing.id
    report.merges.append((existing.id, existing.text, [s.file for s in updated.sources]))
    if existing.manual_done and not mention.source.checked:
        report.notes.append(
            f"{existing.id} was marked done manually but {mention.source.file} lists it as open"
        )


def _refresh_source(store: Store, item_id: str, mention: Mention, report: IngestReport) -> None:
    item = store.items[item_id]
    sources = tuple(
        mention.source if (s.file, s.raw_text) == (mention.source.file, mention.source.raw_text) else s
        for s in item.sources
    )
    refreshed = recompute(replace(item, sources=sources))
    if refreshed != item:
        store.items[item_id] = refreshed
        report.items_updated += 1


def recompute(item: Item) -> Item:
    """Derive status and due date from sources: latest status wins, latest due wins."""
    ordered = tuple(sorted(item.sources, key=lambda s: (s.meeting_date, s.file, s.line)))
    latest = ordered[-1]
    due_iso, due_raw, vague = None, None, False
    for source in reversed(ordered):
        if source.due_phrase:
            result = resolve_due(source.due_phrase, date.fromisoformat(source.meeting_date))
            due_iso, due_raw, vague = result.iso, result.raw, result.vague
            break
    done = latest.checked or item.manual_done
    return replace(
        item,
        sources=ordered,
        due=due_iso,
        due_raw=due_raw,
        due_vague=vague,
        done=done,
        done_at=item.done_at if item.manual_done else None,
    )
