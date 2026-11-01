"""The Redactor: every match of every pattern a team gives is replaced, and nothing else."""

from __future__ import annotations

import re

import pytest
from t2_agentic_voice.core.redaction import Redactor

PHONE = r"05\d{8}"


def test_every_match_of_every_pattern_is_replaced() -> None:
    redact = Redactor([PHONE, r"(?i)ticket \d+"])
    text = "call 0512345678 or 0598765432 about TICKET 77, then Ticket 8"
    assert redact(text) == "call [redacted] or [redacted] about [redacted], then [redacted]"


def test_no_patterns_change_nothing() -> None:
    assert Redactor([])("0512345678 stays") == "0512345678 stays"
    assert Redactor(())("") == ""


def test_overlapping_matches_leave_no_piece_behind() -> None:
    """Applied one after the other, the four-digit pattern would leave `78` of the number; a
    match of any pattern is replaced whole, and a stretch two patterns cover is one marker."""
    redact = Redactor([r"\d{4}", r"\d{10}"])
    assert redact("call 0512345678 now") == "call [redacted] now"
    assert Redactor([r"ab", r"bc"])("xabcx") == "x[redacted]x"
    assert Redactor([r"\d"])("12") == "[redacted][redacted]"


def test_the_replacement_is_never_matched_again() -> None:
    redact = Redactor(["secret", "redact"], replacement="[redacted]")
    assert redact("a secret") == "a [redacted]"


def test_the_replacement_is_taken_as_written() -> None:
    """A backslash or a group reference in it is not expanded, as `re.sub` would."""
    assert Redactor([r"(\d+)"], replacement=r"<\1 gone>")("pin 1234") == r"pin <\1 gone>"


def test_an_empty_match_hides_nothing() -> None:
    assert Redactor([r"x*", PHONE])("ab 0512345678") == "ab [redacted]"


def test_a_bare_string_is_refused() -> None:
    """A str is a sequence of one-letter patterns: each letter would be redacted instead."""
    with pytest.raises(TypeError, match="not one string"):
        Redactor(PHONE)


def test_a_pattern_that_does_not_compile_is_refused() -> None:
    with pytest.raises(re.error):
        Redactor(["("])


def test_its_repr_shows_no_pattern() -> None:
    """A team may write the very value it wants kept out as a pattern."""
    made_up = "gsk_made-up-key-for-tests-0123456789"
    redact = Redactor([re.escape(made_up)])
    assert made_up not in repr(redact)
    assert redact(f"key {made_up}") == "key [redacted]"
