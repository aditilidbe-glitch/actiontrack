"""U9 tests: follow-up drafting and Gmail adapters. Covers R-FUP-01..06, R-SAF-01, R-SAF-03."""

from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import pytest
from helpers import find_item

from actiontrack import gmail
from actiontrack.followup import (
    ACTION_CREATED,
    ACTION_DRY_RUN,
    ACTION_NONE,
    ACTION_UPDATED,
    compose_body,
    compose_subject,
    run_followup,
)
from actiontrack.gmail import (
    ClaudeHeadlessAdapter,
    DraftPayload,
    FakeDraftAdapter,
    GmailError,
    allowed_tools_argument,
    guard_tool,
)
from actiontrack.models import Person
from actiontrack.query import AmbiguousOwnerError, UsageError

TODAY = date(2026, 10, 20)
SRC = Path(__file__).resolve().parent.parent / "src" / "actiontrack"


def test_creates_exactly_one_draft_and_never_sends(ingested, roster) -> None:
    """AC-FUP-01.2, AE6."""
    store, _ = ingested
    fake = FakeDraftAdapter()
    result = run_followup(store, roster, "Karan Joshi", fake, TODAY)
    assert result.action == ACTION_CREATED
    assert [c[0] for c in fake.calls] == ["create_draft"]
    assert store.drafts["karan joshi"] == result.draft_id


def test_subject_and_body_content(ingested, roster) -> None:
    """AC-FUP-01.1, R-FUP-03, R-FUP-06."""
    store, _ = ingested
    fake = FakeDraftAdapter()
    result = run_followup(store, roster, "Karan Joshi", fake, TODAY)
    payload = fake.drafts[result.draft_id]
    assert payload.to == "karan.joshi@example.com"
    assert payload.subject == f"Follow-up: {result.item_count} open action items"
    assert "(OVERDUE)" in payload.body
    assert "no due date" in payload.body
    assert "2026-10-14" not in payload.body or "Acme renewal wrap-up" in payload.body
    done_item = find_item(store, "revoke access for the two ex-contractors")
    assert done_item.text not in payload.body
    open_item = find_item(store, "refund affected customers")
    assert open_item.text in payload.body
    assert "Incident review: billing double-charge (2026-09-21, 2026-09-21-incident-review.md)" in payload.body
    assert payload.body.startswith("Hi Karan,")


def test_subject_singular() -> None:
    assert compose_subject(1) == "Follow-up: 1 open action item"
    assert compose_subject(3) == "Follow-up: 3 open action items"


def test_body_uses_only_store_values(ingested) -> None:
    store, _ = ingested
    item = find_item(store, "refund affected customers")
    body = compose_body("Karan Joshi", [item], TODAY, "<your name>")
    assert "<your name>" in body
    assert "refund affected customers, no due date" in body


def test_second_run_updates_same_draft(ingested, roster) -> None:
    """AC-FUP-04.1."""
    store, _ = ingested
    fake = FakeDraftAdapter()
    first = run_followup(store, roster, "Karan Joshi", fake, TODAY)
    second = run_followup(store, roster, "Karan Joshi", fake, TODAY)
    assert second.action == ACTION_UPDATED and second.draft_id == first.draft_id
    assert len(fake.drafts) == 1


def test_stale_draft_id_creates_a_new_draft(ingested, roster) -> None:
    store, _ = ingested
    store.drafts["karan joshi"] = "gone"
    fake = FakeDraftAdapter()
    result = run_followup(store, roster, "Karan Joshi", fake, TODAY)
    assert result.action == ACTION_CREATED
    assert any("could not be updated" in n for n in result.notes)


def test_missing_email_still_drafts_and_flags(ingested) -> None:
    """R-FUP-03."""
    store, _ = ingested
    fake = FakeDraftAdapter()
    result = run_followup(store, [Person("Karan Joshi")], "Karan Joshi", fake, TODAY)
    assert result.no_recipient and fake.drafts[result.draft_id].to == ""


def test_no_open_items_means_no_draft(ingested, roster) -> None:
    """AC-FUP-01.3."""
    store, _ = ingested
    for item in list(store.items.values()):
        if any(o.name == "Karan Joshi" for o in item.owners):
            from dataclasses import replace

            store.items[item.id] = replace(item, done=True)
    fake = FakeDraftAdapter()
    result = run_followup(store, roster, "Karan Joshi", fake, TODAY)
    assert result.action == ACTION_NONE and fake.calls == []


def test_dry_run_makes_no_adapter_calls(ingested, roster) -> None:
    """R-FUP-05."""
    store, _ = ingested
    fake = FakeDraftAdapter()
    result = run_followup(store, roster, "Karan Joshi", fake, TODAY, dry_run=True)
    assert result.action == ACTION_DRY_RUN and result.payload and fake.calls == []
    assert store.drafts == {}


def test_ambiguous_owner_creates_no_draft(ingested, roster) -> None:
    """AC-FUP-02.1."""
    store, _ = ingested
    fake = FakeDraftAdapter()
    with pytest.raises(AmbiguousOwnerError):
        run_followup(store, roster, "Priya", fake, TODAY)
    assert fake.calls == []


@pytest.mark.parametrize("name", ["unassigned", "everyone"])
def test_group_owners_are_rejected(ingested, roster, name: str) -> None:
    store, _ = ingested
    with pytest.raises(UsageError):
        run_followup(store, roster, name, FakeDraftAdapter(), TODAY)


def test_ambiguous_items_are_excluded_and_counted(ingested, roster) -> None:
    """AC-FUP-02.2."""
    store, _ = ingested
    result = run_followup(store, roster, "Priya Nair", FakeDraftAdapter(), TODAY)
    assert result.excluded_ambiguous > 0


def test_adapter_failure_raises_and_store_unchanged(ingested, roster) -> None:
    """AC-FUP-05.1."""
    store, _ = ingested
    with pytest.raises(GmailError):
        run_followup(store, roster, "Karan Joshi", FakeDraftAdapter(fail=True), TODAY)
    assert store.drafts == {}


def test_missing_adapter_gives_clear_error(ingested, roster) -> None:
    store, _ = ingested
    with pytest.raises(GmailError, match="dry-run"):
        run_followup(store, roster, "Karan Joshi", None, TODAY)


# --- never-send guarantees (R-SAF-01) ---


@pytest.mark.parametrize("tool", ["send_message", "reply", "forward", "trash_thread", "anything_else"])
def test_guard_rejects_non_draft_tools(tool: str) -> None:
    """AC-SAF-01.2."""
    with pytest.raises(GmailError):
        guard_tool(tool)
    with pytest.raises(GmailError):
        FakeDraftAdapter().call(tool)


def test_allowlist_is_drafts_only() -> None:
    assert set(gmail.ALLOWED_TOOLS) == {"create_draft", "update_draft", "get_draft", "list_drafts"}
    assert set(gmail.DENIED_TOOLS) == {"send_message", "reply", "forward"}
    assert not set(gmail.ALLOWED_TOOLS) & set(gmail.DENIED_TOOLS)


_FORBIDDEN = re.compile(
    r"mcp__\w+__(?:send_message|reply|forward)"
    r"|\.(?:send_message|reply|forward)\("
    r"|[\"'](?:send_message|reply|forward)[\"']"
)


def test_source_never_references_send_tools() -> None:
    """AC-SAF-01.1 / 01.3: only the denylist constant may name them."""
    offenders = []
    for path in SRC.glob("*.py"):
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
            if _FORBIDDEN.search(line) and "DENIED_TOOLS" not in line:
                offenders.append(f"{path.name}:{number}: {line.strip()}")
    assert offenders == []


def test_headless_command_allows_only_draft_tools() -> None:
    """Plan U9: argv asserted, subprocess mocked (blocked by the autouse fixture)."""
    adapter = ClaudeHeadlessAdapter(prefix="mcp__x__")
    command = adapter.build_command("create_draft", None, DraftPayload("a@b.co", "S", "B"))
    value = command[command.index("--allowedTools") + 1]
    assert value == allowed_tools_argument("mcp__x__")
    assert not re.search(r"send_message|reply|forward", value)
    assert set(value.split(",")) == {"mcp__x__create_draft", "mcp__x__update_draft", "mcp__x__get_draft"}
    assert not re.search(r"send_message|forward", command[2])


def test_headless_refuses_denied_actions() -> None:
    with pytest.raises(GmailError):
        ClaudeHeadlessAdapter().build_command("send_message", None, DraftPayload("", "", ""))


def test_headless_without_claude_binary_gives_clear_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gmail.shutil, "which", lambda name: None)
    with pytest.raises(GmailError, match="dry-run"):
        ClaudeHeadlessAdapter().create_draft(DraftPayload("", "s", "b"))


def test_real_subprocess_is_blocked_in_tests(monkeypatch: pytest.MonkeyPatch) -> None:
    """AC-FUP-05.2: the guard fixture makes a real call fail loudly."""
    monkeypatch.setattr(gmail.shutil, "which", lambda name: "claude")
    with pytest.raises(AssertionError, match="real Gmail"):
        ClaudeHeadlessAdapter().create_draft(DraftPayload("", "s", "b"))


def test_claude_binary_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ACTIONTRACK_CLAUDE_BIN", "C:/tools/claude.exe")
    command = ClaudeHeadlessAdapter(prefix="p__").build_command("create_draft", None, DraftPayload("", "s", "b"))
    assert command[0] == "C:/tools/claude.exe"
    monkeypatch.delenv("ACTIONTRACK_CLAUDE_BIN")
    assert gmail.claude_binary() == "claude"
