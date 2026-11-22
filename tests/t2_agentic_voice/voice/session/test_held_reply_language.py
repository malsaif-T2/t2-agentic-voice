"""A short turn's reply language as the session reads it (voice/session/talking.py) beside the
talker (agent/turn.py; agent/language.py's held rule, `words.hold_reply_language`): in an
Arabic call held in its language (`session`), a caller who switched to English says "Yes
please", and the talker fails before any clause. The notice the session says in the reply's
language and the talker's prompt name one language: English when the rule is on, the call's
Arabic when it is off, as before. The session decides it from the call's settings and the
talker follows the turn, so a call whose speech-to-text the dev console picked (its settings
the call's, its talker built on the runtime's) still names one. The library's `ChatTalker` on a
fake chat model, in a session on the fake session I/O; every line is written for the test."""

from __future__ import annotations

import asyncio
import dataclasses

import pytest
from t2_agentic_voice.actions.runner import ToolRunner
from t2_agentic_voice.agent.talker import ChatTalker, TalkerCall
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.errors import ProviderError
from t2_agentic_voice.core.settings.stt import LiveLanguage
from t2_agentic_voice.core.settings.tts import LanguageTag
from t2_agentic_voice.core.settings.words import WordSettings
from t2_agentic_voice.voice.session.call import CallSession

from tests.t2_agentic_voice.agent.chat_support import (
    ENGLISH,
    INSTRUCTIONS,
    SAUDI,
    FakeChat,
    agent,
    said,
)
from tests.t2_agentic_voice.session_fakes import FakeSessionIO
from tests.t2_agentic_voice.voice.session.session_support import greeted, play, speaks
from tests.t2_agentic_voice.voice.session.talker_support import talked

AGENT = agent(languages=(SAUDI, ENGLISH))


def _call(
    settings: VoiceSettings, model: FakeChat, talker_settings: VoiceSettings | None = None
) -> FakeSessionIO:
    """An ar-SA call of `AGENT` on `settings`, its talker the library's own on `model`, built on
    `talker_settings` (`settings` unless given)."""
    io = FakeSessionIO(settings, agent=AGENT, language="ar-SA")
    talker = ChatTalker(
        AGENT,
        model=model,
        runner=ToolRunner([]),
        settings=settings if talker_settings is None else talker_settings,
        call=TalkerCall(call_id=io.setup.call_id, caller=io.setup.caller, language="ar-SA"),
        clock=io.clock,
    )
    io.setup = dataclasses.replace(io.setup, talker=talker)
    io.attach(CallSession(io.setup, io.commands))
    return io


@pytest.mark.parametrize(("hold", "expected"), [(True, "en"), (False, "ar-SA")])
def test_the_notice_and_the_prompt_of_a_short_turn_follow_one_tag(
    settings: VoiceSettings, hold: bool, expected: LanguageTag
) -> None:
    held = settings.model_copy(update={"words": WordSettings(hold_reply_language=hold)})
    model = FakeChat(said("Sure, open Settings."), [ProviderError("timeout", True)])
    io = _call(held, model)
    _yes_please(io)
    notice = next(each for each in AGENT.languages if each.tag == expected).notices["error"]
    assert [(s.text, s.language) for s in speaks(io, 2)] == [(notice, expected)]  # talk.language
    assert INSTRUCTIONS[expected] in model.requests[1].messages[0].content  # the talker's tag


@pytest.mark.parametrize(
    ("picked", "runtime", "expected"),
    [
        ("session", "detected", "en"),  # the call never moves: held, as its settings say
        ("detected", "session", "ar-SA"),  # the call may move: not held
    ],
)
def test_a_picked_calls_short_turn_follows_the_calls_settings_not_the_talkers(
    settings: VoiceSettings, picked: LiveLanguage, runtime: LiveLanguage, expected: LanguageTag
) -> None:
    """The dev console's pick (api/stt_choices.py's `chosen_settings`) sets the call's
    `stt.live_language`, while its talker is built on the runtime's: the notice the session says
    and the talker's prompt name one language, the call's settings'."""
    words = WordSettings(hold_reply_language=True)

    def live(mode: LiveLanguage) -> VoiceSettings:
        stt = settings.stt.model_copy(update={"live_language": mode})
        return settings.model_copy(update={"words": words, "stt": stt})

    model = FakeChat(said("Sure, open Settings."), [ProviderError("timeout", True)])
    io = _call(live(picked), model, talker_settings=live(runtime))
    _yes_please(io)
    notice = next(each for each in AGENT.languages if each.tag == expected).notices["error"]
    assert [(s.text, s.language) for s in speaks(io, 2)] == [(notice, expected)]
    assert INSTRUCTIONS[expected] in model.requests[1].messages[0].content


def _yes_please(io: FakeSessionIO) -> None:
    """An English question heard as the call's Arabic, answered in English, then "Yes please",
    heard so too, whose reply fails before any clause."""

    async def drive() -> None:
        await greeted(io)
        await talked(io, 0, "How do I change my password?", language="ar")  # heard as the call's
        await play(io, 1)
        await io.clock.advance(1.0)
        await talked(io, 1, "Yes please", language="ar")
        await play(io, 2)
        await io.ending()
        await io.close()

    asyncio.run(drive())
    assert [s.language for s in speaks(io, 1)] == ["en"]  # the plain English turn, either way
