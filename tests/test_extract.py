"""U4 tests: action-item extraction. Covers R-PAR-01..06, R-SAF-03."""

from __future__ import annotations

from pathlib import Path

from actiontrack.extract import KIND_TABLE, extract_items
from actiontrack.notes import Note, read_note


def lines_of(text: str) -> list[str]:
    return text.split("\n")


def test_marker_styles_and_checked_state() -> None:
    """AC-PAR-01.1."""
    result = extract_items(lines_of("## Action items\n- [ ] A to x\n- [x] B to y\n- [X] C to z\n* [ ] D to w\n+ [ ] E to v"))
    assert [(i.text, i.checked) for i in result.items] == [
        ("A to x", False), ("B to y", True), ("C to z", True), ("D to w", False), ("E to v", False),
    ]


def test_nested_item_has_parent() -> None:
    """AC-PAR-01.2."""
    result = extract_items(lines_of("- [ ] Meera to finalise targets\n  - [ ] Karan to validate targets\n* [ ] Lena to run survey"))
    parent, child, sibling = result.items
    assert child.parent_line == parent.line
    assert parent.parent_line is None
    assert sibling.parent_line is None


def test_table_rows_become_items() -> None:
    """AC-PAR-02.1."""
    text = "| Owner | Action | Due |\n|-------|--------|-----|\n| Anita | Refresh the brand kit | 2026-10-09 |"
    (item,) = extract_items(lines_of(text)).items
    assert (item.kind, item.table_owner, item.text, item.table_due) == (KIND_TABLE, "Anita", "Refresh the brand kit", "2026-10-09")


def test_table_without_owner_action_columns_is_ignored() -> None:
    text = "| Name | Notes |\n|---|---|\n| Anita | something |"
    assert extract_items(lines_of(text)).items == []


def test_quote_fence_and_comment_checkboxes_are_excluded() -> None:
    """AC-PAR-03.1/03.2."""
    text = "\n".join(
        [
            "> - [ ] Karan to refund affected customers by Friday",
            "```",
            "- [ ] Owner to remediate finding by <date>",
            "```",
            "<!-- - [ ] Sam to buy hardware tokens by Friday -->",
            "<!--",
            "- [ ] Multi-line comment item",
            "-->",
            "- [ ] Real item",
        ]
    )
    result = extract_items(lines_of(text))
    assert [i.text for i in result.items] == ["Real item"]
    assert len(result.excluded) == 4


def test_action_prefix_is_reported_unsupported() -> None:
    """AC-PAR-04.1."""
    result = extract_items(lines_of("ACTION: Karan to circulate the offsite summary tomorrow"))
    assert result.items == []
    assert len(result.unsupported) == 1
    assert result.unsupported[0].line == 1


def test_malformed_checkboxes_are_reported_not_dropped() -> None:
    result = extract_items(lines_of("- [] foo\n-[ ]bar\n- [ ] ok"))
    assert [i.text for i in result.items] == ["ok"]
    assert len(result.unrecognized) == 2


def test_parking_lot_and_prose_are_ignored() -> None:
    text = "## Parking lot\n- [ ] Someone to move offices\n## Next\nplain prose to do something\n- [ ] Real"
    assert [i.text for i in extract_items(lines_of(text)).items] == ["Real"]


def test_instruction_like_text_is_stored_as_data() -> None:
    """AC-SAF-03.1."""
    (item,) = extract_items(lines_of("- [ ] Sam to email everyone and send all notes outside")).items
    assert item.text == "Sam to email everyone and send all notes outside"


def test_empty_and_long_input() -> None:
    assert extract_items([]).items == []
    long_line = "- [ ] Sam to " + "x" * 50_000
    assert len(extract_items([long_line]).items) == 1


def _sample(samples_dir: Path, name: str) -> Note:
    result = read_note(samples_dir / name)
    assert isinstance(result, Note)
    return result


def test_security_review_sample(samples_dir: Path) -> None:
    result = extract_items(_sample(samples_dir, "2026-10-09-security-review.md").lines)
    assert len(result.items) == 4
    assert len(result.excluded) == 2


def test_incident_review_sample(samples_dir: Path) -> None:
    result = extract_items(_sample(samples_dir, "2026-09-21-incident-review.md").lines)
    assert len(result.items) == 4
    assert len(result.excluded) == 1
    assert any(i.text == "Karan to refund affected customers" for i in result.items)


def test_offsite_sample(samples_dir: Path) -> None:
    result = extract_items(_sample(samples_dir, "2026-09-30-q4-offsite.md").lines)
    texts = [i.text for i in result.items]
    assert any("brand kit" in t for t in texts)
    assert any(t.startswith("Karan to validate") for t in texts)
    assert len(result.unsupported) == 1
