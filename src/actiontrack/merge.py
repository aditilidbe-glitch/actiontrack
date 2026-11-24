"""Duplicate detection helpers (spec R-DUP-01, R-DUP-02).

Two mentions merge only when their owner keys are equal and the normalized
task texts are similar enough. The threshold is a single named constant.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

from actiontrack.dates import extract_due_phrase
from actiontrack.models import Item, Owner
from actiontrack.owners import owner_key

SIMILARITY_THRESHOLD = 0.6

STOPWORDS = frozenset(
    {
        "a", "an", "the", "to", "of", "for", "with", "by", "and", "on", "in", "at",
        "from", "is", "be", "it", "this", "that", "s", "all", "our", "their",
    }
)
_POSSESSIVE_RE = re.compile(r"['’]s\b", re.IGNORECASE)
_WORD_RE = re.compile(r"[a-z0-9]+")


def task_tokens(task: str) -> frozenset[str]:
    """Normalized token set of a task: no due phrase, stopwords or possessives."""
    phrase = extract_due_phrase(task)
    without_due = task if phrase is None else task[: phrase.start] + " " + task[phrase.end :]
    cleaned = _POSSESSIVE_RE.sub("", without_due.lower())
    return frozenset(t for t in _WORD_RE.findall(cleaned) if t not in STOPWORDS)


def similarity(a: frozenset[str], b: frozenset[str]) -> float:
    """Jaccard similarity of two token sets (0.0 when either is empty)."""
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def owners_key(owners: Iterable[Owner]) -> tuple[str, ...]:
    """Order-independent key for a set of owners."""
    return tuple(sorted(owner_key(o) for o in owners))


def find_best_match(
    items: Iterable[Item],
    key: tuple[str, ...],
    tokens: frozenset[str],
    threshold: float = SIMILARITY_THRESHOLD,
) -> Item | None:
    """Best existing item with the same owner key and similarity >= threshold."""
    best: Item | None = None
    best_score = 0.0
    for item in sorted(items, key=lambda i: i.id):
        if owners_key(item.owners) != key:
            continue
        score = similarity(tokens, task_tokens(item.text))
        if score >= threshold and score > best_score:
            best, best_score = item, score
    return best
