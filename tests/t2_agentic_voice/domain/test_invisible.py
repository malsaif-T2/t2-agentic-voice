"""The characters a spoken phrase may hold that a reader does not see, and the text a provider is
sent for a phrase (domain/text/invisible.py): the no-break spaces sent as spaces, the joiners and
the direction marks dropped, and every other control or format character, separator, lone
surrogate and space but U+0020 refused. The characters are written with `chr`, so this file
holds none of them."""

from __future__ import annotations

import pytest
from t2_agentic_voice.domain.text.invisible import holds_refused_character, provider_text

NBSP, NARROW_NBSP = chr(0x00A0), chr(0x202F)
ZWNJ, ZWJ = chr(0x200C), chr(0x200D)
LRM, RLM, ALM = chr(0x200E), chr(0x200F), chr(0x061C)
# A Saudi greeting as a phone's chat app may paste it: a right-to-left mark before it, and a
# no-break space between two of its words.
SAUDI = "هلا! وش أقدر أساعدك فيه؟"
PASTED = RLM + SAUDI.replace(" ", NBSP, 1)


def test_a_provider_is_sent_plain_spaces_and_no_mark() -> None:
    assert PASTED != SAUDI
    assert provider_text(PASTED) == SAUDI
    assert provider_text(f"a{NBSP}b{NARROW_NBSP}c") == "a b c"
    assert provider_text(f"{ZWNJ}a{ZWJ}b{LRM}c{RLM}d{ALM}e") == "abcde"


def test_every_other_character_is_sent_as_written() -> None:
    """Arabic with its diacritics, digits, punctuation and a plain space are left alone."""
    for text in ("Hi, there! Line 42.", "مَرْحَبًا بِك", SAUDI, "٤٢"):
        assert provider_text(text) == text


def test_a_phrase_may_hold_the_seven_and_a_plain_space() -> None:
    assert not holds_refused_character(PASTED)
    for char in (NBSP, NARROW_NBSP, ZWNJ, ZWJ, LRM, RLM, ALM, " "):
        assert not holds_refused_character(f"a{char}b"), hex(ord(char))
    assert not holds_refused_character("مَرْحَبًا بِك")  # marks on letters are no format characters


@pytest.mark.parametrize(
    "code",
    [
        0x00,  # NULL
        0x09,  # a tab
        0x0A,  # a line feed
        0x0D,  # a carriage return
        0x7F,  # DELETE
        0x85,  # NEXT LINE
        0x2028,  # LINE SEPARATOR
        0x2029,  # PARAGRAPH SEPARATOR
        0x2003,  # EM SPACE
        0x3000,  # IDEOGRAPHIC SPACE
        0x1680,  # OGHAM SPACE MARK
        0x00AD,  # SOFT HYPHEN
        0xFEFF,  # ZERO WIDTH NO-BREAK SPACE, a byte order mark
        0x202E,  # RIGHT-TO-LEFT OVERRIDE
        0x2066,  # LEFT-TO-RIGHT ISOLATE
        0xD800,  # a lone surrogate, which no UTF-8 text holds
    ],
)
def test_every_other_control_format_separator_or_space_is_refused(code: int) -> None:
    assert holds_refused_character(f"a{chr(code)}b")
    assert holds_refused_character(chr(code))
