"""The window measures (plan 002's registration, "Windows"): what a window heard, counted after
the normalizer, against the variant's reference."""

from __future__ import annotations

from collections.abc import Sequence

import pytest
from ole5_voice.evals.windows import leading_words, measure, measurer

from tests.ole5_voice.evals.fakes import FakeMatcher, fake_normalize


def _measure(
    reference: str, text: str, *, reused: bool = False, ms: int = 500
) -> dict[str, object]:
    window = measure(
        reference,
        ms,
        text,
        reused=reused,
        normalize=fake_normalize,
        is_right=FakeMatcher().is_right,
    )
    return window.model_dump()


@pytest.mark.parametrize(
    ("reference", "heard", "count"),
    [
        ("stop now", "stop", 1),
        ("stop now", "stop now please", 2),
        ("open the inbox", "open the", 2),
        ("open the inbox", "the inbox", 0),  # in order, from the first word
        ("open the inbox", "open a inbox", 1),
        ("open the inbox", "", 0),
        ("", "open", 0),
    ],
)
def test_leading_words_counts_the_run_both_texts_begin_with(
    reference: str, heard: str, count: int
) -> None:
    assert leading_words(reference, heard) == count


def test_a_window_is_measured_after_the_normalizer() -> None:
    found = _measure("Open the inbox, please.", "OPEN the In-")
    assert found == {
        "ms": 500,
        "text": "OPEN the In-",  # kept as heard
        "empty": False,
        "words": 3,  # open, the, in
        "leading_words": 2,
        "holds_word": None,  # only for a reference of one word
        "reused": False,
    }


def test_an_empty_window_and_a_window_of_punctuation_hear_nothing() -> None:
    for text in ("", "  ", "..."):
        found = _measure("open the inbox", text)
        assert (found["empty"], found["words"], found["leading_words"]) == (True, 0, 0)


def test_a_one_word_reference_is_held_when_any_run_of_words_says_it() -> None:
    assert _measure("Okay.", "uh okay")["holds_word"] is True
    assert _measure("okay", "o kay")["holds_word"] is True  # a word split in two, as the matcher
    assert _measure("okay", "ok")["holds_word"] is False
    assert _measure("okay", "")["holds_word"] is False


def test_holding_a_word_is_the_matchers_call_with_the_reference_alone() -> None:
    calls: list[tuple[str, tuple[str, ...]]] = []

    def is_right(output: str, references: Sequence[str]) -> bool:
        calls.append((output, tuple(references)))
        return output == "b"

    window = measure("Yes", 750, "a b", reused=True, normalize=fake_normalize, is_right=is_right)
    assert (window.holds_word, window.reused, window.ms) == (True, True, 750)
    assert calls == [("a", ("Yes",)), ("a b", ("Yes",)), ("b", ("Yes",))]


def test_a_silence_reference_has_no_word_to_hold() -> None:
    found = _measure("", "thank you")
    assert (found["words"], found["leading_words"], found["holds_word"]) == (2, 0, None)


def test_the_measurer_binds_a_runs_normalizer_and_matcher() -> None:
    measured = measurer(fake_normalize, FakeMatcher().is_right)
    window = measured("stop", 1000, "Stop!", True)
    assert (window.ms, window.words, window.holds_word, window.reused) == (1000, 1, True, True)
