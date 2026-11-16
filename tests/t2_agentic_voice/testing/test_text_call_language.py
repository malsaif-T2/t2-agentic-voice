"""A typed turn is heard in the call's language as it stands (testing/text_parts.py's
`hand_typed`; plan 010, run F's switch calls): once the call has moved under
`stt.live_language = "detected"`, a short turn in the new language is heard, and so answered, in
it, as a real call's speech-to-text, told the new language, would hear it; a call that never
moved hears every turn in the language it joined in. The turn that asked for the move is heard
in the language it was said in (its reply follows its `asked`, talking.py); each language is
the heard code."""

from __future__ import annotations

import asyncio

from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.conversation import TalkerTurn

from tests.t2_agentic_voice.testing.text_call_support import ScriptedCall, Step, answer


def _script(turn: TalkerTurn) -> list[Step]:
    if turn.language == "en" or turn.asked == "en":
        return answer("Sure, which city?")
    return answer("أبشر، وش المدينة؟", language="ar-SA")


def _detected() -> VoiceSettings:
    settings = VoiceSettings(env="test")
    stt = settings.stt.model_copy(update={"live_language": "detected"})
    return settings.model_copy(update={"stt": stt})


def _heard(settings: VoiceSettings, said: tuple[str, ...]) -> list[str | None]:
    async def scene() -> list[str | None]:
        async with ScriptedCall(_script, settings=settings, language="ar-SA") as call:
            for words in said:
                await call.user(words)
                await call.advance(10.0)
            assert call.talker is not None
            return [turn.language for turn in call.talker.turns]

    return asyncio.run(scene())


def test_after_the_call_moved_a_short_turn_is_heard_in_the_new_language() -> None:
    assert _heard(_detected(), ("بالانجليزي لو سمحت", "Yes.")) == ["ar", "en"]


def test_a_call_that_never_moved_hears_each_turn_in_its_own_language() -> None:
    assert _heard(_detected(), ("ودي أحجز", "Yes.")) == ["ar", "ar"]
    assert _heard(VoiceSettings(env="test"), ("بالانجليزي لو سمحت", "Yes.")) == ["ar", "ar"]
