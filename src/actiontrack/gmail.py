"""Gmail draft adapters (spec R-SAF-01, R-FUP-05).

HARD RULE: drafts only. Only the allowlisted tools may ever be called. The
denylist below exists solely so tests can assert these names are never used.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from typing import Protocol

from actiontrack.models import ActionTrackError

TOOL_CREATE_DRAFT = "create_draft"
TOOL_UPDATE_DRAFT = "update_draft"
TOOL_GET_DRAFT = "get_draft"
TOOL_LIST_DRAFTS = "list_drafts"
ALLOWED_TOOLS = (TOOL_CREATE_DRAFT, TOOL_UPDATE_DRAFT, TOOL_GET_DRAFT, TOOL_LIST_DRAFTS)
HEADLESS_TOOLS = (TOOL_CREATE_DRAFT, TOOL_UPDATE_DRAFT, TOOL_GET_DRAFT)

# DENYLIST: mail-delivering tools that must never be called (tests assert this).
DENIED_TOOLS = ("send_message", "reply", "forward")

ENV_TOOL_PREFIX = "ACTIONTRACK_GMAIL_TOOL_PREFIX"
DEFAULT_TOOL_PREFIX = "mcp__claude_ai_Gmail__"
CLAUDE_BINARY = "claude"
ENV_CLAUDE_BIN = "ACTIONTRACK_CLAUDE_BIN"
HEADLESS_TIMEOUT_SECONDS = 180


class GmailError(ActionTrackError):
    """Draft creation failed or the connector is unavailable."""


@dataclass(frozen=True)
class DraftPayload:
    """What goes into a draft. `to` may be empty (R-FUP-03)."""

    to: str
    subject: str
    body: str


class DraftAdapter(Protocol):
    def create_draft(self, payload: DraftPayload) -> str: ...

    def update_draft(self, draft_id: str, payload: DraftPayload) -> str: ...


def guard_tool(tool: str) -> None:
    """Raise unless `tool` is on the draft allowlist."""
    if tool in DENIED_TOOLS or tool not in ALLOWED_TOOLS:
        raise GmailError(f"tool '{tool}' is not allowed: actiontrack only creates drafts")


@dataclass
class FakeDraftAdapter:
    """In-memory adapter for tests. Records every call by tool name."""

    calls: list[tuple[str, object]] = field(default_factory=list)
    drafts: dict[str, DraftPayload] = field(default_factory=dict)
    fail: bool = False

    def call(self, tool: str, *args: object) -> None:
        guard_tool(tool)
        self.calls.append((tool, args))

    def create_draft(self, payload: DraftPayload) -> str:
        self.call(TOOL_CREATE_DRAFT, payload)
        if self.fail:
            raise GmailError("simulated Gmail failure")
        draft_id = f"fake-draft-{len(self.drafts) + 1}"
        self.drafts[draft_id] = payload
        return draft_id

    def update_draft(self, draft_id: str, payload: DraftPayload) -> str:
        self.call(TOOL_UPDATE_DRAFT, draft_id, payload)
        if self.fail:
            raise GmailError("simulated Gmail failure")
        if draft_id not in self.drafts:
            raise GmailError(f"draft {draft_id} no longer exists")
        self.drafts[draft_id] = payload
        return draft_id


def claude_binary() -> str:
    """Path or name of the claude CLI; override with ACTIONTRACK_CLAUDE_BIN."""
    return os.environ.get(ENV_CLAUDE_BIN, CLAUDE_BINARY)


def tool_prefix() -> str:
    return os.environ.get(ENV_TOOL_PREFIX, DEFAULT_TOOL_PREFIX)


def allowed_tools_argument(prefix: str) -> str:
    """Comma-separated allowed-tools value for the headless call: draft tools only."""
    return ",".join(prefix + name for name in HEADLESS_TOOLS)


def _prompt(action: str, draft_id: str | None, payload: DraftPayload) -> str:
    data = json.dumps({"draft_id": draft_id, "to": payload.to, "subject": payload.subject, "body": payload.body})
    return (
        f"Use the Gmail tool {action} exactly once with the JSON data below as the draft fields "
        "(an empty 'to' means no recipient). Do not call any other tool. "
        "Reply with only the resulting draft id on a single line.\n"
        f"DATA: {data}"
    )


class ClaudeHeadlessAdapter:
    """Creates drafts through a headless `claude -p` call limited to draft tools."""

    def __init__(self, prefix: str | None = None) -> None:
        self.prefix = prefix if prefix is not None else tool_prefix()

    def build_command(self, action: str, draft_id: str | None, payload: DraftPayload) -> list[str]:
        guard_tool(action)
        return [
            claude_binary(),
            "-p",
            _prompt(action, draft_id, payload),
            "--allowedTools",
            allowed_tools_argument(self.prefix),
            "--output-format",
            "text",
        ]

    def _run(self, action: str, draft_id: str | None, payload: DraftPayload) -> str:
        if shutil.which(claude_binary()) is None:
            raise GmailError(
                f"the claude CLI '{claude_binary()}' was not found; set {ENV_CLAUDE_BIN} or use --dry-run"
            )
        command = self.build_command(action, draft_id, payload)
        try:
            done = subprocess.run(
                command, capture_output=True, text=True, encoding="utf-8",
                timeout=HEADLESS_TIMEOUT_SECONDS, check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise GmailError(f"Gmail draft call failed: {exc}; try --dry-run") from exc
        lines = [ln.strip() for ln in done.stdout.splitlines() if ln.strip()]
        if done.returncode != 0 or not lines:
            raise GmailError(f"Gmail draft call failed (exit {done.returncode}); try --dry-run")
        return lines[-1]

    def create_draft(self, payload: DraftPayload) -> str:
        return self._run(TOOL_CREATE_DRAFT, None, payload)

    def update_draft(self, draft_id: str, payload: DraftPayload) -> str:
        return self._run(TOOL_UPDATE_DRAFT, draft_id, payload)
