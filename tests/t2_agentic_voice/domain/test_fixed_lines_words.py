"""No fixed line of the library holds a word of the presets' lists (plan 006, "What voice-first
means here", item 6): a line the agent speaks as written (each preset's echo frame and notices,
and the lines an action may leave to the library; a team gives its greeting and its progress
lines) may be heard back as its own echo, so a stop, wait, repeat or listening word in it could
stop the agent, or keep it going, on its own voice. The test names the kinds it reads, so a kind
added to the lists fails it until it is read too. The yes rule's words (plan 007): no such line
holds a yes word, so its echo can never confirm an action, and only the ask-again line, which
asks the closing question again, holds a send word. The Ole5 app's lines have the same test of
their own."""

from __future__ import annotations

import pytest
from t2_agentic_voice.domain.presets import ACTION_LINES, ECHO_FRAMES, NOTICES
from t2_agentic_voice.domain.text.words import holds_words
from t2_agentic_voice.domain.words import PRESET_WORDS, WORD_KINDS, rule_form
from t2_agentic_voice.domain.yes_words import PRESET_CONSENT

# The kinds of word a line's echo must not hold: all but the no words, which only a short
# output's rule reads (domain/interruptions.py), and which ordinary sentences hold.
CHECKED = ("stop", "wait", "repeat", "backchannel")
LINES = [
    *((f"echo_frame {tag}", text) for tag, text in ECHO_FRAMES.items()),
    *(
        (f"notices.{kind} {tag}", text)
        for tag, notices in NOTICES.items()
        for kind, text in notices.items()
    ),
    *(
        (f"action.{field} {tag}", text)
        for tag, lines in ACTION_LINES.items()
        for field, text in lines.items()
    ),
]


def _held(text: str, words: tuple[str, ...]) -> list[str]:
    said = rule_form(text)
    return [word for word in words if holds_words(said, rule_form(word))]


def test_the_test_reads_every_kind_of_list_but_the_no_words() -> None:
    assert set(WORD_KINDS) - {"no"} == set(CHECKED)


@pytest.mark.parametrize(("name", "text"), LINES, ids=[name for name, _ in LINES])
def test_a_fixed_line_holds_no_word_of_any_presets_lists(name: str, text: str) -> None:
    held = [
        (code, kind, word)
        for code, words in PRESET_WORDS.items()
        for kind in CHECKED
        for word in _held(text, getattr(words, kind))
    ]
    assert held == [], f"{name} holds words of the presets' lists"


@pytest.mark.parametrize(("name", "text"), LINES, ids=[name for name, _ in LINES])
def test_a_fixed_line_holds_no_yes_word(name: str, text: str) -> None:
    held = [word for consent in PRESET_CONSENT.values() for word in _held(text, consent.yes)]
    assert held == [], f"{name} holds a yes word, whose echo could confirm an action"


@pytest.mark.parametrize(("name", "text"), LINES, ids=[name for name, _ in LINES])
def test_only_the_ask_again_line_holds_a_send_word(name: str, text: str) -> None:
    if name.startswith("action.asked_again"):
        return
    held = [word for consent in PRESET_CONSENT.values() for word in _held(text, consent.send)]
    assert held == [], f"{name} holds a send word"


def test_the_check_finds_a_listed_word_in_a_line() -> None:
    """The test is not blind: a line holding a wait word, or a yes word, is caught."""
    assert _held("لحظة، أشيك لك", PRESET_WORDS["ar"].wait)
    assert _held("Sure, sending it now.", PRESET_CONSENT["en"].yes) == ["sure"]
