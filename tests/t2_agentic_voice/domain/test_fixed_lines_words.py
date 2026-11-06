"""No fixed line of the library holds a word of the presets' lists (plan 006, "What voice-first
means here", item 6): a line the agent speaks as written (each preset's echo frame and notices;
a team gives its greeting and its progress lines) may be heard back as its own echo, so a stop,
wait, repeat or listening word in it could stop the agent, or keep it going, on its own voice.
The yes and send words come with the yes rule; the test names the kinds it reads, so a kind
added to the lists fails it until it is read too. The Ole5 app's lines have the same test of
their own."""

from __future__ import annotations

import pytest
from t2_agentic_voice.domain.presets import ECHO_FRAMES, NOTICES
from t2_agentic_voice.domain.text.words import holds_words
from t2_agentic_voice.domain.words import PRESET_WORDS, WORD_KINDS, rule_form

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
]


def test_the_test_reads_every_kind_of_list_but_the_no_words() -> None:
    assert set(WORD_KINDS) - {"no"} == set(CHECKED)


@pytest.mark.parametrize(("name", "text"), LINES, ids=[name for name, _ in LINES])
def test_a_fixed_line_holds_no_word_of_any_presets_lists(name: str, text: str) -> None:
    said = rule_form(text)
    held = [
        (code, kind, word)
        for code, words in PRESET_WORDS.items()
        for kind in CHECKED
        for word in getattr(words, kind)
        if holds_words(said, rule_form(word))
    ]
    assert held == [], f"{name} holds words of the presets' lists"


def test_the_check_finds_a_listed_word_in_a_line() -> None:
    """The test is not blind: a line holding a wait word is caught."""
    said = rule_form("لحظة، أشيك لك")
    assert any(holds_words(said, rule_form(word)) for word in PRESET_WORDS["ar"].wait)
