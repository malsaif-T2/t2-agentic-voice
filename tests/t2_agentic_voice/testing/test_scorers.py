"""wer and cer: pooled error rates on jiwer, after the scorers' normalization, against
hand-computed cases; an empty reference refused, since jiwer would then give a count."""

from __future__ import annotations

from collections.abc import Callable, Sequence

import jiwer
import pytest
from t2_agentic_voice.testing.scorers import cer, wer

Scorer = Callable[[Sequence[str], Sequence[str]], float]


@pytest.mark.parametrize(
    ("references", "outputs", "rate"),
    [
        (["a b c"], ["a b c"], 0.0),
        (["a b c"], ["a x c"], 1 / 3),  # one substitution over 3 words
        (["a b c"], ["a c"], 1 / 3),  # one deletion
        (["a b"], ["a b c d"], 1.0),  # two insertions over 2 words
        (["a"], ["a b c"], 2.0),  # insertions take the rate above 1
        (["a b"], [""], 1.0),  # an empty output: every word deleted
        (["a b", "c d e"], ["a b", "c"], 2 / 5),  # pooled: 2 errors over 5 words
        (["a", "b c d e"], ["x", "b c d e"], 1 / 5),  # pooled, not a mean of 1 and 0
        (["a b c"], ["c b a"], 2 / 3),  # two substitutions; the middle word aligns
    ],
)
def test_wer_on_hand_computed_cases(references: list[str], outputs: list[str], rate: float) -> None:
    assert wer(references, outputs) == pytest.approx(rate)


@pytest.mark.parametrize(
    ("references", "outputs", "rate"),
    [
        (["abc"], ["abc"], 0.0),
        (["abc"], ["abd"], 1 / 3),
        (["abcd"], ["abd"], 1 / 4),
        (["a"], ["abc"], 2.0),
        (["ab"], [""], 1.0),
        (["ab", "cdef"], ["ab", "cd"], 2 / 6),  # pooled over 6 characters
        (["تمام"], ["تمم"], 1 / 4),  # one Arabic letter lost of four
    ],
)
def test_cer_on_hand_computed_cases(references: list[str], outputs: list[str], rate: float) -> None:
    assert cer(references, outputs) == pytest.approx(rate)


def test_both_sides_are_normalized_before_scoring() -> None:
    reference, heard = ["أرسل الملف PDF على Outlook"], ["ارسل الملف، pdf علي outlook؟"]
    assert wer(reference, heard) == cer(reference, heard) == 0.0
    assert wer(["رسالة"], ["رساله"]) == 0.0


def test_digits_said_one_at_a_time_count_as_the_digits_the_reference_writes() -> None:
    reference = ["رقم التذكرة 4521"]
    for heard in ["رقم التذكرة أربعة خمسة اثنين واحد", "رقم التذكرة ٤٥٢١", "رقم التذكرة 4 5 2 1"]:
        assert wer(reference, [heard]) == cer(reference, [heard]) == 0.0


def test_a_word_split_differently_costs_words_but_no_character() -> None:
    # The verdict removes spaces, and so does CER, so the split is not counted twice; WER
    # counts the words as written: one substitution and one deletion over two words.
    assert cer(["لو سمحت"], ["لوسمحت"]) == 0.0
    assert wer(["لو سمحت"], ["لوسمحت"]) == 1.0


def test_a_format_character_inside_a_word_splits_it_for_wer_alone() -> None:
    # Pinned as the prototype's normalizer has it (TD-008): a zero-width non-joiner reads as a
    # space, so WER counts a substitution and an insertion where CER counts nothing.
    split = "لو" + chr(0x200C) + "سمحت"
    assert (wer(["لوسمحت"], [split]), cer(["لوسمحت"], [split])) == (2.0, 0.0)


def test_cer_counts_no_space_as_a_character() -> None:
    assert cer(["a b"], ["ab"]) == 0.0
    assert cer(["ab"], ["a b c"]) == 1 / 2  # one inserted c over the 2 characters


@pytest.mark.parametrize("scorer", [wer, cer])
def test_a_rate_is_always_a_float(scorer: Scorer) -> None:
    assert type(scorer(["a"], ["a"])) is float
    assert type(scorer(["a"], ["a b"])) is float


@pytest.mark.parametrize("scorer", [wer, cer])
def test_any_sequence_of_texts_is_read(scorer: Scorer) -> None:
    assert scorer(("a b",), ("a b",)) == 0.0


def test_jiwer_itself_gives_the_insertions_count_when_the_reference_has_no_words() -> None:
    # The reason for the refusal below, read in jiwer 4.0.0's process.py ("special edge-case for
    # empty references": the WER is the number of insertions) and checked here.
    assert jiwer.wer("", "a b") == 2
    assert jiwer.wer(["", "a"], ["x y", "a"]) == 2.0


@pytest.mark.parametrize("scorer", [wer, cer])
@pytest.mark.parametrize("empty", ["", "   ", "؟!.", "\u064e\u0651", "\u200f"])
def test_a_reference_empty_after_normalization_is_refused(scorer: Scorer, empty: str) -> None:
    with pytest.raises(ValueError, match="reference 1 is empty after normalization"):
        scorer(["a b", empty, "c"], ["a b", "x y", "c"])


@pytest.mark.parametrize("scorer", [wer, cer])
def test_outputs_and_references_of_different_lengths_are_refused(scorer: Scorer) -> None:
    with pytest.raises(ValueError, match="2 references and 1 outputs"):
        scorer(["a", "b"], ["a"])


@pytest.mark.parametrize("scorer", [wer, cer])
def test_no_pairs_are_refused(scorer: Scorer) -> None:
    with pytest.raises(ValueError, match="no pairs to score"):
        scorer([], [])


@pytest.mark.parametrize("scorer", [wer, cer])
@pytest.mark.parametrize(
    ("references", "outputs", "name"),
    [("a b", ["a b"], "references"), (["a b"], "a b", "outputs"), ("ab", "ab", "references")],
)
def test_a_bare_str_is_refused_since_it_would_be_scored_letter_by_letter(
    scorer: Scorer, references: Sequence[str], outputs: Sequence[str], name: str
) -> None:
    with pytest.raises(TypeError, match=f"{name} is a sequence of texts, not one str"):
        scorer(references, outputs)


@pytest.mark.parametrize("scorer", [wer, cer])
@pytest.mark.parametrize(
    ("references", "outputs"),
    [([None], ["a"]), (["a"], [None]), ([b"a"], ["a"]), (b"ab", ["a", "b"])],
)
def test_anything_but_a_str_inside_is_refused(
    scorer: Scorer, references: Sequence[object], outputs: Sequence[object]
) -> None:
    with pytest.raises(TypeError, match="every reference and every output is a str"):
        scorer(references, outputs)  # type: ignore[arg-type]
