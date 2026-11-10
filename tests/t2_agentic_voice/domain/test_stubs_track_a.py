"""The stubs plan 007's Block 0 left for Track A, each raising with the track's name. Track A
deletes this file as it fills them."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from t2_agentic_voice.core.settings.guard import GuardSettings
from t2_agentic_voice.core.yes_inputs import HEARD_WORDS_SEAL, HeardWords
from t2_agentic_voice.domain.action_flow import advance
from t2_agentic_voice.domain.action_lines import default_action_lines
from t2_agentic_voice.domain.claims import check_claims, default_claims
from t2_agentic_voice.domain.yes_rule import decide
from t2_agentic_voice.domain.yes_words import ConsentWords, consent_words
from t2_agentic_voice.voice.session.read_back import played_receipt

WORDS = ConsentWords(yes=("yes",), send=("send",), no=("no",), fillers=("please",))


def _heard() -> HeardWords:
    values = {"turn_id": 9, "text": "made up", "language": "en", "at": 9.0, "speech_at": 8.0}
    return HeardWords.model_validate(values, context=HEARD_WORDS_SEAL)


def _receipt() -> Any:
    return played_receipt(
        action="open_request",
        draft_json='{"summary": "made up"}',
        reply_id=4,
        summary_played_at=6.0,
        question_ended_at=None,
    )


STUBS: dict[str, Callable[[], Any]] = {
    "decide": lambda: decide(_heard(), _receipt(), words=WORDS, env="test"),
    "consent_words": lambda: consent_words("en"),
    "advance": lambda: advance("confirming", "yes"),
    "check_claims": lambda: check_claims(
        "made up", claims={}, any_action=(), evidence=(), settings=GuardSettings(), year=2026
    ),
    "default_claims": lambda: default_claims("en"),
    "default_action_lines": lambda: default_action_lines("en"),
}


@pytest.mark.parametrize("call", STUBS.values(), ids=STUBS.keys())
def test_a_stub_raises_naming_track_a(call: Callable[[], Any]) -> None:
    with pytest.raises(NotImplementedError, match="Track A"):
        call()
