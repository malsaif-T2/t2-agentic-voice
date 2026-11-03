"""Whether speech over the agent's reply stops it (domain/interruptions.py): an overlap's
transcript and the rule's verdict are frozen and bounded, the verdict's kind and reason the
`Interrupted` event's, and `judge` is a stub until plan 005's Track A builds the starting rule,
its tests written on texts made for them, never an item's."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import get_args

import pytest
from pydantic import ValidationError
from t2_agentic_voice.core.events import Interrupted, InterruptionReason
from t2_agentic_voice.domain.interruptions import Overlap, Verdict, VerdictReason, judge
from t2_agentic_voice.domain.words import PRESET_WORDS

AT = datetime(2026, 11, 3, 12, 0, tzinfo=UTC)

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


def test_a_verdicts_kind_and_reason_are_what_its_event_carries() -> None:
    verdict = Verdict(action="repeat", kind="stop", reason="repeat_word")
    event = Interrupted(call_id="c-1", at=AT, kind=verdict.kind, reason=verdict.reason)
    assert (event.kind, event.reason) == ("stop", "repeat_word")
    assert get_args(VerdictReason) == get_args(InterruptionReason)  # one list for both


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
