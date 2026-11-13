"""Which calls classify each turn's language (voice/stt_language.py's `turn_languages`): only under
`stt.live_language = "classified"`, with a classifier, for an agent of two codes or more; any other
call names the session's language on every request, `session`. And what a decided turn's request
carries for run H (testing/turn_languages.py): when its language was decided, at its hold's start or
its close, and the seconds of its speech then."""

from __future__ import annotations

import asyncio

from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.settings.stt import SttSettings
from t2_agentic_voice.domain.declaration import Language, VoiceAgent
from t2_agentic_voice.domain.turn_language import LanguageRule
from t2_agentic_voice.voice.session.io import SYSTEM_CLOCK
from t2_agentic_voice.voice.stt_language import TurnLanguages, turn_languages
from t2_agentic_voice.voice.stt_turn import HeldTurn

from tests.t2_agentic_voice.fakes import FakeClock
from tests.t2_agentic_voice.language_fakes import FakeLanguageClassifier
from tests.t2_agentic_voice.session_fakes import AGENT

RATE = 16_000


async def _settle() -> None:
    """Let the classification's task run to its end."""
    for _ in range(20):
        await asyncio.sleep(0)


def _turn(turn_id: int, seconds: float) -> HeldTurn:
    """A turn holding `seconds` of audio, its speech from its first byte."""
    return HeldTurn(turn_id=turn_id, audio=bytearray(b"\x00\x00" * int(RATE * seconds)), speech=0)


def test_a_decided_turn_carries_when_it_was_decided_and_its_speech_then() -> None:
    """The hold's start decides a classified turn, the close a turn with no hold; each request's
    `Transcribing` carries that time, on the call's clock, and the speech held then. A call that
    classifies nothing carries neither."""
    clock = FakeClock(start=10.0)

    async def body() -> None:
        classifier = FakeLanguageClassifier([{"ar": 0.1, "en": 0.9}])
        rule = LanguageRule(from_s=2.0, min_share=0.7)
        languages = TurnLanguages(clock=clock, classifier=classifier, codes=("ar", "en"), rule=rule)
        languages.listen_in("ar")
        long = _turn(0, 2.5)
        languages.heard(long, RATE)
        await _settle()
        await clock.advance(1.5)
        languages.held(long, RATE, began=True)
        held = languages.named(0, "turn").transcribing(0, at=12.0, audio_s=2.5, part="turn")
        assert (held.language, held.language_by) == ("en", "classified")
        assert (held.decided_at, held.speech_s) == (11.5, 2.5)
        await clock.advance(2.0)
        languages.closed(_turn(1, 1.0), RATE)
        short = languages.named(1, "turn")
        assert (short.language, short.by, short.decided_at, short.speech_s) == (
            "en",
            "short",
            13.5,
            1.0,
        )
        session = TurnLanguages(clock=clock).named(0, "turn")
        assert (session.decided_at, session.speech_s) == (None, None)

    asyncio.run(body())


def test_the_bridge_classifies_only_under_classified_for_an_agent_of_two_codes() -> None:
    """With no classifier, one code, or another setting, every request names the session's
    language, `session`."""
    classifier = FakeLanguageClassifier()
    classified = VoiceSettings(env="test", stt=SttSettings(live_language="classified"))
    session = VoiceSettings(env="test")
    english = VoiceAgent(name="english", languages=[Language.english(greeting="Hello.")])
    for agent, settings, given, classifies in (
        (AGENT, classified, classifier, True),
        (AGENT, classified, None, False),
        (english, classified, classifier, False),
        (AGENT, session, classifier, False),
    ):
        languages = turn_languages(agent, settings, given, SYSTEM_CLOCK)
        assert languages.classifies is classifies
        languages.listen_in("en")
        named = languages.named(0, "turn")
        if not classifies:
            assert (named.language, named.by) == ("en", "session")
    assert TurnLanguages(clock=SYSTEM_CLOCK).named(3, "window").by == "session"
