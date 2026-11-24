"""Command-line interface (spec R-RPT-01: exit 0 ok, 1 error, 2 usage/ambiguity).

Data goes to stdout; messages and errors go to stderr. Commands: ingest,
list, done, followup. Drafts only; nothing in this program sends email.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Callable, Sequence
from datetime import date, datetime
from pathlib import Path
from typing import TextIO

from actiontrack.followup import ACTION_NONE, FollowupResult, run_followup
from actiontrack.gmail import ClaudeHeadlessAdapter, DraftAdapter
from actiontrack.ingest import IngestReport, ingest_folder
from actiontrack.models import EXIT_ERROR, EXIT_OK, EXIT_USAGE, ActionTrackError, Person
from actiontrack.owners import owner_display
from actiontrack.query import (
    ListFilters,
    ListResult,
    UsageError,
    assign_owner,
    list_items,
    mark_done,
    parse_iso_date,
    validate_status,
)
from actiontrack.roster import DEFAULT_ROSTER_NAME, load_roster
from actiontrack.store import DEFAULT_STORE_RELPATH, Store, load_store, save_store

ENV_TODAY = "ACTIONTRACK_TODAY"
TEXT_WIDTH = 60

AdapterFactory = Callable[[], DraftAdapter]


def _common_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--store", type=Path, default=None, help="store file (default .actiontrack/store.json)")
    common.add_argument("--people", type=Path, default=None, help="roster file (default ./people.json if present)")
    common.add_argument("--today", default=None, help="override today's date (YYYY-MM-DD)")
    return common


def build_parser() -> argparse.ArgumentParser:
    common = _common_parser()
    parser = argparse.ArgumentParser(prog="actiontrack", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    ingest = sub.add_parser("ingest", parents=[common], help="ingest a folder of markdown notes")
    ingest.add_argument("folder", type=Path)
    ingest.add_argument("--recursive", action="store_true")
    listing = sub.add_parser("list", parents=[common], help="list action items")
    listing.add_argument("--owner")
    listing.add_argument("--status")
    listing.add_argument("--due-before", dest="due_before")
    listing.add_argument("--json", action="store_true", dest="as_json")
    done = sub.add_parser("done", parents=[common], help="mark an item done")
    done.add_argument("id")
    assign = sub.add_parser("assign", parents=[common], help="resolve an ambiguous owner to one person")
    assign.add_argument("id")
    assign.add_argument("owner", help="full name of the person")
    follow = sub.add_parser("followup", parents=[common], help="draft (never send) a Gmail follow-up")
    follow.add_argument("owner")
    follow.add_argument("--dry-run", action="store_true", dest="dry_run")
    return parser


def _today(args: argparse.Namespace) -> date:
    text = args.today or os.environ.get(ENV_TODAY)
    return parse_iso_date(text, "--today") if text else date.today()


def _roster(args: argparse.Namespace, err: TextIO) -> list[Person]:
    path = args.people
    if path is None:
        default = Path(DEFAULT_ROSTER_NAME)
        if not default.exists():
            print("warning: no roster file; emails are unavailable", file=err)
            return []
        path = default
    return load_roster(path)


def _store_path(args: argparse.Namespace) -> Path:
    return args.store or DEFAULT_STORE_RELPATH


def _truncate(text: str, width: int = TEXT_WIDTH) -> str:
    return text if len(text) <= width else text[: width - 3] + "..."


def format_ingest(report: IngestReport) -> str:
    lines = [
        "Ingest summary",
        f"  files seen: {report.files_seen}",
        f"  ingested: {report.ingested}",
        f"  skipped: {len(report.skipped)}",
    ]
    lines.extend(f"    - {s.file}: {s.reason}" for s in report.skipped)
    lines.append(f"  items: {report.items_new} new, {report.items_updated} updated, {len(report.merges)} merged")
    lines.extend(f"    merged {i} ({_truncate(t)}) from {', '.join(f)}" for i, t, f in report.merges)
    lines.append(f"  excluded (quoted/code/comment checkboxes): {report.excluded}")
    lines.extend(f"  unsupported: {f}:{x.line}: {x.reason} {_truncate(x.text)}" for f, x in report.unsupported)
    lines.extend(f"  unrecognized: {f}:{x.line}: {_truncate(x.text)}" for f, x in report.unrecognized)
    lines.extend(f"  warning: {w}" for w in report.warnings)
    lines.extend(f"  note: {n}" for n in report.notes)
    return "\n".join(lines)


def format_list(result: ListResult) -> str:
    header = f"{'ID':<10} {'OWNER':<22} {'DUE':<11} {'STATUS':<8} TEXT"
    rows = [header]
    for view in result.items:
        item = view.item
        owner = ", ".join(owner_display(o) for o in item.owners)
        due = item.due or (f"? {item.due_raw}" if item.due_raw else "-")
        rows.append(f"{item.id:<10} {_truncate(owner, 22):<22} {_truncate(due, 11):<11} {view.status:<8} {_truncate(item.text)}")
    rows.append(f"{len(result.items)} item(s)")
    return "\n".join(rows)


def list_as_json(result: ListResult) -> str:
    payload = [{**v.item.to_dict(), "status": v.status} for v in result.items]
    return json.dumps(payload, indent=2, ensure_ascii=False)


def _cmd_ingest(args: argparse.Namespace, out: TextIO, err: TextIO) -> int:
    if not args.folder.is_dir():
        raise ActionTrackError(f"folder not found: {args.folder}")
    path = _store_path(args)
    store = load_store(path)
    report = ingest_folder(args.folder, store, _roster(args, err), recursive=args.recursive)
    save_store(path, store)
    print(format_ingest(report), file=out)
    return EXIT_OK


def _cmd_list(args: argparse.Namespace, out: TextIO, err: TextIO) -> int:
    validate_status(args.status)
    due_before = parse_iso_date(args.due_before, "--due-before") if args.due_before else None
    store = load_store(_store_path(args))
    filters = ListFilters(args.owner, args.status, due_before)
    result = list_items(store, _roster(args, err), filters, _today(args))
    print(list_as_json(result) if args.as_json else format_list(result), file=out)
    for note in result.notes:
        print(f"note: {note}", file=err)
    return EXIT_OK


def _cmd_done(args: argparse.Namespace, out: TextIO, err: TextIO) -> int:
    path = _store_path(args)
    store = load_store(path)
    result = mark_done(store, args.id, datetime.now())
    if result.changed:
        save_store(path, store)
        print(f"marked {result.item.id} done", file=out)
    else:
        print(f"{result.item.id} is already done", file=out)
    return EXIT_OK


def _cmd_assign(args: argparse.Namespace, out: TextIO, err: TextIO) -> int:
    path = _store_path(args)
    store = load_store(path)
    result = assign_owner(store, _roster(args, err), args.id, args.owner)
    if result.changed:
        save_store(path, store)
        print(f"assigned {result.item.id} to {args.owner}", file=out)
    else:
        print(f"{result.item.id} is already assigned to {args.owner}", file=out)
    return EXIT_OK


def format_followup(result: FollowupResult) -> str:
    if result.action == ACTION_NONE:
        lines = [f"No open action items for {result.owner}; no draft created."]
    elif result.action == "dry-run" and result.payload:
        p = result.payload
        lines = [f"DRY RUN: no draft created for {result.owner}", f"To: {p.to}", f"Subject: {p.subject}", "", p.body]
    else:
        lines = [f"DRAFT {result.action}, not sent (id {result.draft_id}) for {result.owner}: {result.item_count} item(s)"]
    if result.no_recipient and result.action != ACTION_NONE:
        lines.append("NO RECIPIENT: add email to people.json")
    if result.excluded_ambiguous:
        lines.append(f"{result.excluded_ambiguous} item(s) with an ambiguous owner were left out")
    lines.extend(result.notes)
    return "\n".join(lines)


def _cmd_followup(
    args: argparse.Namespace, out: TextIO, err: TextIO, factory: AdapterFactory
) -> int:
    path = _store_path(args)
    store = load_store(path)
    adapter = None if args.dry_run else factory()
    result = run_followup(store, _roster(args, err), args.owner, adapter, _today(args), args.dry_run)
    if not args.dry_run:
        save_store(path, store)
    print(format_followup(result), file=out)
    return EXIT_OK


def _use_utf8_console() -> None:
    """Avoid mojibake/crashes on Windows consoles with legacy code pages."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")


def main(
    argv: Sequence[str] | None = None,
    out: TextIO | None = None,
    err: TextIO | None = None,
    adapter_factory: AdapterFactory = ClaudeHeadlessAdapter,
) -> int:
    """Run the CLI and return the exit code."""
    _use_utf8_console()
    out, err = out or sys.stdout, err or sys.stderr
    try:
        args = build_parser().parse_args(argv)
    except SystemExit as exc:
        return EXIT_OK if exc.code in (0, None) else EXIT_USAGE
    try:
        if args.command == "ingest":
            return _cmd_ingest(args, out, err)
        if args.command == "list":
            return _cmd_list(args, out, err)
        if args.command == "done":
            return _cmd_done(args, out, err)
        if args.command == "assign":
            return _cmd_assign(args, out, err)
        return _cmd_followup(args, out, err, adapter_factory)
    except UsageError as exc:
        print(f"error: {exc}", file=err)
        return EXIT_USAGE
    except ActionTrackError as exc:
        print(f"error: {exc}", file=err)
        return EXIT_ERROR
