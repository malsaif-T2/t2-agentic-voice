"""Whether speech over the agent's reply stops it (domain/interruptions.py): an overlap's
transcript and the rule's verdict are frozen and bounded, and `judge` is a stub until plan 005's
Track A builds the starting rule, its tests written on texts made for them, never an item's."""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from t2_agentic_voice.domain.interruptions import Overlap, Verdict, judge
from t2_agentic_voice.domain.words import PRESET_WORDS

OVERLAP = Overlap(
    text="made-up words over the reply",
    no_speech_prob=0.1,
    speech_s=1.2,
    played=("a made-up clause the agent said",),
    language="en",
)


def test_an_overlap_and_a_verdict_are_frozen_and_bounded() -> None:
    verdict = Verdict(action="go_on", kind="false", reason="own_words")
    with pytest.raises(ValidationError):
        OVERLAP.text = "changed"  # type: ignore[misc]
    with pytest.raises(ValidationError):
        verdict.action = "stop"  # type: ignore[misc]
    for wrong in ({"no_speech_prob": 1.5}, {"speech_s": -1.0}, {"language": "fr"}):
        with pytest.raises(ValidationError):
            Overlap.model_validate(OVERLAP.model_dump() | wrong)
    with pytest.raises(ValidationError):
        Verdict.model_validate({"action": "pause", "kind": "stop", "reason": "stop_word"})
    assert Overlap(text="", speech_s=0.0, language="ar").played == ()


def test_judge_is_a_stub_until_the_rule_is_built() -> None:
    with pytest.raises(NotImplementedError, match="Track A"):
        judge(
            OVERLAP,
            words=PRESET_WORDS["en"],
            no_speech_max=None,
            captions=(),
            min_words=2,
            short_words=2,
            short_s=1.6,
        )
