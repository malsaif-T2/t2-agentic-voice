"""The pronunciation map (domain/text/pronounce.py): each written form that stands as whole words
said as the call's language says it, in one pass. The entries here are made up for the test; an
app's own entries are the app's data."""

from __future__ import annotations

from types import MappingProxyType

from t2_agentic_voice.domain.text.pronounce import Pronunciations, pronounce
from t2_agentic_voice.languages import pronounce as public_pronounce

ENTRIES: Pronunciations = {
    "LT-": {"ar": "إل تي", "en": "L T"},
    "Zed9": {"ar": "زد ناين", "en": "Zed nine"},
    "Al": {"en": "A L"},
    "طقم": {"ar": "طَقْم"},
}


def test_the_facade_gives_the_same_function() -> None:
    assert public_pronounce is pronounce


def test_a_form_is_said_as_the_language_says_it() -> None:
    assert pronounce("Ask Zed9 today", ENTRIES, language="en") == "Ask Zed nine today"
    assert pronounce("اسأل Zed9 اليوم", ENTRIES, language="ar") == "اسأل زد ناين اليوم"


def test_both_arabic_tags_share_the_arabic_entry() -> None:
    assert pronounce("Zed9", ENTRIES, language="ar-SA") == "زد ناين"
    assert pronounce("Zed9", ENTRIES, language="ar") == "زد ناين"


def test_a_form_with_no_entry_for_the_language_is_left_as_written() -> None:
    assert pronounce("Al and طقم", ENTRIES, language="ar") == "Al and طَقْم"
    assert pronounce("Al and طقم", ENTRIES, language="en") == "A L and طقم"


def test_a_form_is_found_only_as_whole_words() -> None:
    assert pronounce("Ali, Alps and Al.", ENTRIES, language="en") == "Ali, Alps and A L."
    assert pronounce("xZed9 Zed99 Zed9x Zed9", ENTRIES, language="en") == (
        "xZed9 Zed99 Zed9x Zed nine"
    )
    assert pronounce("الطقم وطقم طقمين طقم", ENTRIES, language="ar") == "الطقم وطقم طقمين طَقْم"


def test_an_arabic_mark_belongs_to_its_word() -> None:
    entries: Pronunciations = {"قم": {"ar": "X"}, "طق": {"ar": "Y"}}
    # A haraka or a sukun after a form's last letter, or before its first, is still its word's.
    assert pronounce("طقْم مَقم", entries, language="ar") == "طقْم مَقم"
    assert pronounce("طق، قم", entries, language="ar") == "Y، X"


def test_a_form_that_ends_in_a_mark_is_found_against_the_word_after_it() -> None:
    assert pronounce("tag LT-00423 and LT- alone", ENTRIES, language="en") == (
        "tag L T 00423 and L T alone"
    )
    assert pronounce("الجهاز LT-00423", ENTRIES, language="ar-SA") == "الجهاز إل تي 00423"


def test_a_form_is_found_as_written_case_included() -> None:
    assert pronounce("ZED9 zed9 Zed9", ENTRIES, language="en") == "ZED9 zed9 Zed nine"


def test_the_longest_form_wins_where_two_start_at_one_place() -> None:
    entries: Pronunciations = {"Zed": {"en": "short"}, "Zed one": {"en": "long"}}
    assert pronounce("Zed one and Zed", entries, language="en") == "long and short"


def test_a_said_form_is_never_looked_in_again() -> None:
    entries: Pronunciations = {"A": {"en": "B"}, "B": {"en": "C"}}
    assert pronounce("A B", entries, language="en") == "B C"


def test_an_empty_map_leaves_the_text() -> None:
    text = "Made-up LT- words"
    assert pronounce(text, {}, language="en") == text
    assert pronounce(text, {"Q": {"ar": "R"}}, language="en") == text


def test_a_read_only_map_as_the_declaration_keeps_it() -> None:
    entries = MappingProxyType({"LT-": MappingProxyType({"en": "L T"})})
    assert pronounce("LT-7", entries, language="en") == "L T 7"


def test_a_form_of_marks_only_is_found_anywhere() -> None:
    entries: Pronunciations = {"->": {"en": " then "}}
    assert pronounce("menu->users", entries, language="en") == "menu then users"
