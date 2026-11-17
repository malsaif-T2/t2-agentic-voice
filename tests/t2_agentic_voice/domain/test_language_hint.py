"""The rule `stt.live_language = "hinted"` moves a call by (domain/language_hint.py, D-115): a
turn's one answer moves it when its language is one of the agent's other languages, heard with
a probability at or above the threshold, in a question or request; each condition alone
refuses, and an answer with no probability never moves it; and `single`'s rule (D-117) holds a
gate and a hint of one agent's languages."""

from __future__ import annotations

import pytest
from t2_agentic_voice.domain.language_hint import HintRule, SingleRule, hinted_move, hinted_switch
from t2_agentic_voice.domain.language_switch import DetectRule

RULE = HintRule(min_probability=0.8, codes=("ar", "en"))
QUESTION = "Which flights go to Dubai tomorrow?"
WHERE = "وين الرحلات"  # wain al-rihlat, where are the flights


def _switch(
    heard: str | None, probability: float | None, text: str = QUESTION, named: str = "ar"
) -> str | None:
    return hinted_switch(named, heard, probability, text=text, rule=RULE)


def test_an_english_question_heard_surely_in_an_arabic_call_moves_it() -> None:
    assert _switch("en", 0.95) == "en"
    assert _switch("en-US", 0.8) == "en"  # at the threshold, and with a region
    assert _switch("English", 0.9) == "en"  # Whisper's name of it
    assert _switch("ar", 0.99, WHERE, named="en") == "ar"


@pytest.mark.parametrize(
    ("heard", "probability", "text"),
    [
        ("ar", 0.99, QUESTION),  # the language the request named: no move
        ("fr", 0.99, QUESTION),  # a language the agent does not speak
        (None, 0.99, QUESTION),  # no language reported
        ("en", 0.79, QUESTION),  # under the threshold
        ("en", None, QUESTION),  # no probability given
        ("en", 0.99, "okay"),  # a short reply of one word
        ("en", 0.99, "Yes, okay, thanks."),  # only short replies
    ],
)
def test_each_condition_alone_refuses_the_move(
    heard: str | None, probability: float | None, text: str
) -> None:
    assert _switch(heard, probability, text) is None


def test_the_move_without_the_threshold_reads_the_language_and_words_alone() -> None:
    assert hinted_move("ar", "en", codes=RULE.codes, text=QUESTION) == "en"
    assert hinted_move("ar", "en", codes=RULE.codes, text="okay") is None
    assert hinted_move("en", "en", codes=RULE.codes, text=QUESTION) is None


def test_the_rule_gives_the_other_languages_beside_the_one_named() -> None:
    assert RULE.others("ar") == ("en",)
    assert RULE.others("en-US") == ("ar",)
    assert RULE.others(None) == ("ar", "en")


@pytest.mark.parametrize(
    ("probability", "codes"), [(0.0, ("ar", "en")), (1.01, ("ar", "en")), (0.8, ("ar", "ar"))]
)
def test_a_rule_out_of_range_or_of_one_language_is_refused(
    probability: float, codes: tuple[str, ...]
) -> None:
    with pytest.raises(ValueError, match=r"probability|two of the agent"):
        HintRule(min_probability=probability, codes=codes)  # type: ignore[arg-type]


def test_singles_rule_holds_a_gate_and_a_hint_of_one_agents_languages() -> None:
    gate = DetectRule(from_s=1.2, codes=("ar", "en"))
    rule = SingleRule(gate=gate, hint=RULE)
    assert rule.gate.detects(1.2) and not rule.gate.detects(1.1) and not rule.gate.detects(None)
    with pytest.raises(ValueError, match="one agent's languages"):
        SingleRule(gate=DetectRule(from_s=1.2, codes=("ar", "fr")), hint=RULE)  # type: ignore[arg-type]
