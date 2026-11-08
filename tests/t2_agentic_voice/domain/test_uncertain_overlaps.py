"""A chat model's word on an uncertain overlap, its pure parts (domain/uncertain_overlaps.py;
D-069, plan 006, Q28): which verdicts of the rule ask the model, on what count of words as the
rule splits them; the request the eval and the call share; and the answer read from the model's
text. The session's side is voice/session/test_overlap_ask.py's."""

from __future__ import annotations

import pytest
from t2_agentic_voice.domain.interruptions import Verdict, word_count
from t2_agentic_voice.domain.uncertain_overlaps import (
    MODEL_STOP,
    UNCERTAIN_OVERLAP_INSTRUCTION,
    is_uncertain,
    uncertain_overlap_answer,
    uncertain_overlap_request,
)
from t2_agentic_voice.domain.words import PRESET_WORDS

WORDS = PRESET_WORDS["en"]
SHORT = Verdict(action="go_on", kind="false", reason="short_output")
TOO_FEW = Verdict(action="go_on", kind="false", reason="too_few_words")


def test_the_model_is_asked_on_two_or_more_words_the_rule_lets_go_on_for_want_of_them() -> None:
    assert is_uncertain(SHORT, "need agent", words=WORDS)
    assert is_uncertain(TOO_FEW, "okay agent please", words=WORDS)
    assert not is_uncertain(SHORT, "agent", words=WORDS)  # a single word keeps the rule


@pytest.mark.parametrize("reason", ["no_words", "own_words", "listening"])
def test_any_other_reason_to_go_on_is_not_asked(reason: str) -> None:
    verdict = Verdict(action="go_on", kind="false", reason=reason)  # type: ignore[arg-type]
    assert not is_uncertain(verdict, "need agent now", words=WORDS)


def test_a_stop_is_not_asked() -> None:
    stop = Verdict(action="stop", kind="stop", reason="stop_word")
    assert not is_uncertain(stop, "need agent", words=WORDS)


def test_a_listed_phrase_is_one_word_as_the_rule_splits_it() -> None:
    assert "go on" in WORDS.backchannel
    assert word_count("go on", words=WORDS) == 1
    assert word_count("please go on now", words=WORDS) == 3
    assert word_count("", words=WORDS) == 0


def test_the_request_is_the_shape_run_u_ran() -> None:
    request = uncertain_overlap_request("the agent's reply", "need agent")
    system, user = request.messages
    assert (system.role, system.content) == ("system", UNCERTAIN_OVERLAP_INSTRUCTION)
    assert user.content == (
        "The agent was saying:\nthe agent's reply\n\nThe caller said over it:\nneed agent"
    )
    assert (request.model, request.reasoning_effort, request.max_output_tokens) == (
        "openai/gpt-oss-120b",
        "low",
        256,
    )
    assert request.temperature == 0.0 and request.tools == ()


def test_the_request_takes_an_arms_own_model_and_bounds() -> None:
    request = uncertain_overlap_request(
        "x", "y", model="llama-3.1-8b-instant", reasoning_effort=None, max_output_tokens=16
    )
    assert (request.model, request.reasoning_effort, request.max_output_tokens) == (
        "llama-3.1-8b-instant",
        None,
        16,
    )


def test_the_model_stop_is_new_words_with_a_reason_of_its_own() -> None:
    assert (MODEL_STOP.action, MODEL_STOP.kind, MODEL_STOP.reason) == ("stop", "new_words", "model")


def test_the_answer_is_read_as_run_u_read_it() -> None:
    cases = {"Stop.": "stop", "go_on": "go_on", " Go On! ": "go_on", "maybe": "unclear"}
    assert {text: uncertain_overlap_answer(text) for text in cases} == cases
