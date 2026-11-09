"""The clause splitter on a streamed text (domain/text/clauses.py's `ClauseStream`): each clause
given as soon as it is whole, and the clauses given, in order, exactly `split_clauses` of the
whole text however it was cut into pieces."""

from __future__ import annotations

import random

import pytest
from t2_agentic_voice.domain.text.clauses import ClauseStream, split_clauses

TEXTS = [
    "Open Settings, then press Reset. It takes 3.5 minutes!",
    "افتح الإعدادات، ثم اضغط إعادة التعيين. هل تحتاج شيئا آخر؟ «تم.»",
    "No mark at the end at all",
    "Visit t2.example and wait… then retry; done.",
    "Spaces and\ttabs,\nand lines . . end.",
    "x" * 230 + " short, " + "word " * 60,
    "",
    "   ",
]


def _streamed(text: str, cuts: list[int], max_chars: int | None) -> tuple[str, ...]:
    stream = ClauseStream(max_chars=max_chars)
    clauses: list[str] = []
    at = 0
    for cut in [*cuts, len(text)]:
        clauses += stream.feed(text[at:cut])
        at = cut
    return (*clauses, *stream.close())


@pytest.mark.parametrize("text", TEXTS)
@pytest.mark.parametrize("max_chars", [None, 200, 12])
def test_any_cut_of_the_text_gives_split_clauses_of_the_whole(
    text: str, max_chars: int | None
) -> None:
    whole = split_clauses(text, max_chars=max_chars)
    assert _streamed(text, [], max_chars) == whole
    assert _streamed(text, list(range(1, len(text))), max_chars) == whole  # one character a piece
    pick = random.Random(len(text))  # noqa: S311 - deterministic cuts of a text, no secret
    for _ in range(20):
        cuts = sorted(pick.sample(range(len(text) + 1), min(len(text), pick.randint(0, 8))))
        assert _streamed(text, cuts, max_chars) == whole


def test_a_clause_is_given_once_a_space_follows_its_last_word() -> None:
    stream = ClauseStream(max_chars=None)
    assert stream.feed("Open Settings") == ()
    assert stream.feed(", then") == ("Open Settings,",)
    assert stream.feed(" press Reset.") == ()  # "Reset." may still go on ("Reset.com")
    assert stream.feed(" It") == ("then press Reset.",)
    assert stream.close() == ("It",)
    assert stream.close() == ()


def test_a_limit_under_one_is_refused() -> None:
    with pytest.raises(ValueError, match="at least 1"):
        ClauseStream(max_chars=0)


def _whole(text: str) -> tuple[str, ...]:
    stream = ClauseStream(max_chars=None, whole_sentences=True)
    return (*stream.feed(text), *stream.close())


def test_whole_sentences_cut_only_at_a_sentences_end() -> None:
    """D-077: the English voice sounds out of breath when each comma starts a new request."""
    assert _whole("Open it, then press Archive: choose a reason; press Save. It is done!") == (
        "Open it, then press Archive: choose a reason; press Save.",
        "It is done!",
    )


def test_whole_sentences_cut_at_a_comma_once_the_clause_is_long() -> None:
    long = "word " * 24 + "last,"  # 124 characters
    assert _whole(f"Short, still going, {long} and the end.") == (
        f"Short, still going, {long}",
        "and the end.",
    )
