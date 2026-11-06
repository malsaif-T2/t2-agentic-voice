"""The reply language of a turn (agent/language.py; plan 006, item 8): the heard language,
overruled by the turn's script only when it plainly says otherwise, mapped to the agent's tag,
the call's own first."""

from __future__ import annotations

import pytest
from t2_agentic_voice.agent.language import reply_language
from t2_agentic_voice.core.conversation import TalkerTurn
from t2_agentic_voice.core.settings.tts import LanguageTag

SPOKEN: list[LanguageTag] = ["ar-SA", "ar", "en"]


def _language(words: str, heard: str | None, call: LanguageTag = "ar-SA") -> LanguageTag:
    turn = TalkerTurn(turn_id=0, words=words, language=heard)
    return reply_language(turn, call=call, spoken=SPOKEN)


@pytest.mark.parametrize(
    ("words", "heard", "call", "expected"),
    [
        ("ابي اغير كلمة السر", "ar", "ar-SA", "ar-SA"),
        ("أريد تغيير كلمة المرور", "ar", "ar-SA", "ar-SA"),  # MSA: the tag stays, the prompt asks
        ("ابي اغير كلمة السر", "ar", "ar", "ar"),  # the call's own Arabic tag
        ("How do I change my password?", "en", "ar-SA", "en"),
        ("How do I change my password?", "ar", "ar-SA", "en"),  # Latin letters in an Arabic call
        ("VPN Outlook Teams ما يشتغل", "ar", "ar-SA", "ar-SA"),  # product terms stay Arabic
        ("Outlook ما يفتح", "ar", "ar-SA", "ar-SA"),
        ("ابي اغير كلمة السر لو سمحت", "en", "en", "ar-SA"),  # Arabic letters in an English call
        ("hello", None, "en", "en"),
        ("hello", "Arabic", "en", "ar-SA"),  # a provider's name of the language
        ("مرحبا", "fr", "ar", "ar"),  # a language the agent has no tag for: the call's
    ],
)
def test_the_reply_follows_the_turns_language(
    words: str, heard: str | None, call: LanguageTag, expected: LanguageTag
) -> None:
    assert _language(words, heard, call) == expected


def test_an_agent_with_no_tag_in_the_language_keeps_the_calls() -> None:
    turn = TalkerTurn(turn_id=0, words="How do I change my password?", language="en")
    assert reply_language(turn, call="ar-SA", spoken=["ar-SA"]) == "ar-SA"
