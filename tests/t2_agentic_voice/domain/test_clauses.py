"""The clause splitter (domain/text/clauses.py): a text cut at the Arabic comma and question mark,
the full stop and English punctuation, every clause within `max_chars`, none cut inside a word
but a word longer than `max_chars`. Every text here is written for the test."""

from __future__ import annotations

import pytest
from t2_agentic_voice.domain.text.clauses import split_clauses
from t2_agentic_voice.languages import split_clauses as public_split_clauses


def test_the_facade_gives_the_same_function() -> None:
    assert public_split_clauses is split_clauses


def test_an_arabic_text_is_cut_at_its_comma_question_mark_and_full_stop() -> None:
    text = "هلا والله، وش تبي أسوي لك اليوم؟ الجهاز جاهز. شكرا"
    assert split_clauses(text, max_chars=200) == (
        "هلا والله،",
        "وش تبي أسوي لك اليوم؟",
        "الجهاز جاهز.",
        "شكرا",
    )


def test_the_arabic_semicolon_and_full_stop_cut_too() -> None:
    assert split_clauses("أولا؛ ثانيا۔ ثالثا", max_chars=None) == ("أولا؛", "ثانيا۔", "ثالثا")


def test_an_english_text_is_cut_at_its_punctuation() -> None:
    text = "Well, the desk is free; take it: now. Ready? Go! Then wait… and rest"
    assert split_clauses(text, max_chars=200) == (
        "Well,",
        "the desk is free;",
        "take it:",
        "now.",
        "Ready?",
        "Go!",
        "Then wait…",
        "and rest",
    )


def test_a_mark_inside_a_word_cuts_nothing() -> None:
    text = "Version 3.5 runs at 12:30 on t2.example, today"
    assert split_clauses(text, max_chars=200) == (
        "Version 3.5 runs at 12:30 on t2.example,",
        "today",
    )


def test_quotes_and_brackets_after_a_mark_stay_with_its_clause() -> None:
    text = 'He said "yes." Then (maybe, later) she left «تمام،» بعدين'
    assert split_clauses(text, max_chars=None) == (
        'He said "yes."',
        "Then (maybe,",
        "later) she left «تمام،»",
        "بعدين",
    )


def test_a_mixed_text_keeps_its_order() -> None:
    text = "تمام، the laptop is ready. وش بعد؟ Nothing else"
    assert split_clauses(text, max_chars=200) == (
        "تمام،",
        "the laptop is ready.",
        "وش بعد؟",
        "Nothing else",
    )


def test_a_long_clause_is_cut_between_words_within_max_chars() -> None:
    words = [f"word{n}" for n in range(60)]
    text = " ".join(words)
    clauses = split_clauses(text, max_chars=40)
    assert all(len(clause) <= 40 for clause in clauses)
    assert " ".join(clauses).split() == words  # no word cut, lost or moved
    assert all(len(clauses[n]) + 1 + len(clauses[n + 1].split()[0]) > 40 for n in range(5))


def test_every_clause_of_a_long_arabic_text_fits_and_no_word_is_cut() -> None:
    sentence = "الجهاز ما يشبك على الشبكة من الصباح وأبغى أحد يساعدني بسرعة لو سمحت، "
    text = sentence * 12
    clauses = split_clauses(text, max_chars=50)
    assert all(0 < len(clause) <= 50 for clause in clauses)
    assert " ".join(clauses).split() == text.split()


def test_a_word_longer_than_max_chars_is_cut_every_max_chars() -> None:
    assert split_clauses("x" * 201, max_chars=200) == ("x" * 200, "x")
    assert split_clauses("y" * 400, max_chars=200) == ("y" * 200, "y" * 200)


def test_words_around_a_long_word_end_before_it_and_start_after_it() -> None:
    text = f"one two {'z' * 12} three four"
    said = ("one", "two", "zzzzz", "zzzzz", "zz", "three", "four")
    assert split_clauses(text, max_chars=5) == said
    assert split_clauses(f"ab cd {'q' * 7} ef", max_chars=6) == ("ab cd", "qqqqqq", "q", "ef")


def test_no_limit_cuts_only_at_marks() -> None:
    text = "a " * 300 + "end. next"
    assert split_clauses(text, max_chars=None) == (("a " * 300 + "end.").strip(), "next")


def test_a_text_with_nothing_to_say_gives_no_clause() -> None:
    for text in ["", "   ", " . ، ؟ ", "...", "\n\t"]:
        assert split_clauses(text, max_chars=200) == ()


def test_no_clause_is_empty_or_only_marks() -> None:
    assert split_clauses("Hello. . . world", max_chars=200) == ("Hello.", "world")
    # A symbol is said.
    assert split_clauses("Price: $5? +", max_chars=200) == ("Price:", "$5?", "+")


def test_spaces_between_words_become_one() -> None:
    assert split_clauses("  many   spaces\nand a\u00a0line  ", max_chars=200) == (
        "many spaces and a line",
    )


@pytest.mark.parametrize("max_chars", [0, -1])
def test_max_chars_is_at_least_one(max_chars: int) -> None:
    with pytest.raises(ValueError, match="at least 1"):
        split_clauses("text", max_chars=max_chars)
