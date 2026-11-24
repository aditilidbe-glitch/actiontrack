"""Action-item extraction from note lines (spec R-PAR-01..06, R-SAF-03).

A small line-based state machine: tracks fenced code, HTML comments, block
quotes, headings and tables. Note text is treated purely as data.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

KIND_CHECKBOX = "checkbox"
KIND_TABLE = "table"
UNSUPPORTED_ACTION_PREFIX = "unsupported format: ACTION:"
UNRECOGNIZED_CHECKBOX = "unrecognized checkbox"

_CHECKBOX_RE = re.compile(r"^(?P<indent>\s*)[-*+]\s+\[(?P<mark>[ xX])\]\s+(?P<text>\S.*?)\s*$")
_CHECKBOX_ANYWHERE_RE = re.compile(r"[-*+]\s+\[[ xX]\]\s+\S")
_MALFORMED_RE = re.compile(r"^\s*[-*+]\s*\[[ xX]?\]\S*")
_FENCE_RE = re.compile(r"^\s*(```|~~~)")
_ACTION_RE = re.compile(r"^\s*(?:[-*+]\s+)?ACTION:\s*(?P<text>.+?)\s*$")
_TABLE_ROW_RE = re.compile(r"^\s*\|(?P<body>.+)\|\s*$")
_SEPARATOR_CELL_RE = re.compile(r"^:?-{2,}:?$|^:?-+:?$")
_HEADING_RE = re.compile(r"^\s*#{1,6}\s+(?P<title>.+?)\s*$")
_PARKING_LOT_RE = re.compile(r"parking\s+lot", re.IGNORECASE)
_COMMENT_OPEN = "<!--"
_COMMENT_CLOSE = "-->"


@dataclass(frozen=True)
class RawItem:
    """An action item as found in a note, before owner/date interpretation."""

    text: str
    checked: bool
    line: int
    kind: str = KIND_CHECKBOX
    parent_line: int | None = None
    table_owner: str | None = None
    table_due: str | None = None


@dataclass(frozen=True)
class Finding:
    """A line that was reported but not tracked."""

    line: int
    text: str
    reason: str


@dataclass
class ExtractResult:
    items: list[RawItem] = field(default_factory=list)
    excluded: list[Finding] = field(default_factory=list)
    unsupported: list[Finding] = field(default_factory=list)
    unrecognized: list[Finding] = field(default_factory=list)


@dataclass
class _State:
    in_fence: bool = False
    in_comment: bool = False
    in_parking_lot: bool = False
    pending_header: list[str] | None = None
    table_columns: dict[str, int] | None = None
    open_items: list[tuple[int, int]] = field(default_factory=list)  # (indent, line)


def _cells(body: str) -> list[str]:
    return [cell.strip() for cell in body.split("|")]


def _is_separator(cells: list[str]) -> bool:
    return bool(cells) and all(_SEPARATOR_CELL_RE.match(c) for c in cells if c)


def _column_map(header: list[str]) -> dict[str, int] | None:
    lowered = [h.lower() for h in header]
    if "owner" in lowered and "action" in lowered:
        columns = {"owner": lowered.index("owner"), "action": lowered.index("action")}
        if "due" in lowered:
            columns["due"] = lowered.index("due")
        return columns
    return None


def _handle_table_row(state: _State, cells: list[str], line_no: int, result: ExtractResult) -> None:
    if _is_separator(cells):
        if state.pending_header is not None:
            state.table_columns = _column_map(state.pending_header)
        return
    if state.table_columns is None:
        state.pending_header = cells
        return
    columns = state.table_columns
    action = _cell(cells, columns["action"])
    if not action:
        return
    result.items.append(
        RawItem(
            text=action,
            checked=False,
            line=line_no,
            kind=KIND_TABLE,
            table_owner=_cell(cells, columns["owner"]) or None,
            table_due=_cell(cells, columns["due"]) if "due" in columns else None,
        )
    )


def _cell(cells: list[str], index: int) -> str:
    return cells[index] if index < len(cells) else ""


def _update_comment_state(state: _State, line: str) -> bool:
    """Return True if this line is inside (or opens/closes) an HTML comment."""
    if state.in_comment:
        if _COMMENT_CLOSE in line:
            state.in_comment = False
        return True
    if _COMMENT_OPEN in line:
        if _COMMENT_CLOSE not in line.split(_COMMENT_OPEN, 1)[1]:
            state.in_comment = True
        return True
    return False


def _is_excluded_context(state: _State, line: str) -> bool:
    """True when the line sits in a fence, comment or block quote."""
    if _FENCE_RE.match(line):
        state.in_fence = not state.in_fence
        return True
    if state.in_fence:
        return True
    if _update_comment_state(state, line):
        return True
    return line.lstrip().startswith(">")


def _add_checkbox(state: _State, match: re.Match[str], line_no: int, result: ExtractResult) -> None:
    indent = len(match.group("indent").expandtabs(4))
    state.open_items = [(i, ln) for i, ln in state.open_items if i < indent]
    parent = state.open_items[-1][1] if state.open_items else None
    state.open_items.append((indent, line_no))
    result.items.append(
        RawItem(
            text=match.group("text"),
            checked=match.group("mark") in "xX",
            line=line_no,
            parent_line=parent,
        )
    )


def _process_line(state: _State, line: str, line_no: int, result: ExtractResult) -> None:
    if _is_excluded_context(state, line):
        if _CHECKBOX_ANYWHERE_RE.search(line):
            result.excluded.append(Finding(line_no, line.strip(), "quoted/code/comment"))
        return
    if heading := _HEADING_RE.match(line):
        state.in_parking_lot = bool(_PARKING_LOT_RE.search(heading.group("title")))
        state.open_items.clear()
        return
    if state.in_parking_lot:
        return
    _process_content_line(state, line, line_no, result)


def _process_content_line(state: _State, line: str, line_no: int, result: ExtractResult) -> None:
    if table := _TABLE_ROW_RE.match(line):
        _handle_table_row(state, _cells(table.group("body")), line_no, result)
        return
    state.pending_header = None
    state.table_columns = None
    if match := _CHECKBOX_RE.match(line):
        _add_checkbox(state, match, line_no, result)
    elif _MALFORMED_RE.match(line):
        result.unrecognized.append(Finding(line_no, line.strip(), UNRECOGNIZED_CHECKBOX))
    elif action := _ACTION_RE.match(line):
        result.unsupported.append(Finding(line_no, action.group("text"), UNSUPPORTED_ACTION_PREFIX))


def extract_items(lines: tuple[str, ...] | list[str]) -> ExtractResult:
    """Extract tracked items plus excluded/unsupported/unrecognized findings."""
    result = ExtractResult()
    state = _State()
    for index, line in enumerate(lines, start=1):
        _process_line(state, line, index, result)
    return result
