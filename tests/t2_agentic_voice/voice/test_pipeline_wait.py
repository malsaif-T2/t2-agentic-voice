"""A read-back's longer wait in a call's pipeline (voice/pipeline.py; plan 010's 1.11): with
`turns.read_back_silence_ms` set, the pipeline holds a `LongerWait` of its seconds that the
session's `ReadBackWait` turns on and off; unset, it holds none, and the command does nothing."""

from __future__ import annotations

import asyncio

import pytest
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.identity import Caller, Consent
from t2_agentic_voice.core.settings.turns import TurnSettings
from t2_agentic_voice.voice.pipeline import CallPipeline
from t2_agentic_voice.voice.session.commands import ReadBackWait
from t2_agentic_voice.voice.turn_hold import LongerWait

from tests.t2_agentic_voice.fakes import Captured, capturing_output
from tests.t2_agentic_voice.session_fakes import AGENT
from tests.t2_agentic_voice.voice.kit import PauseAnalyzer, ToneVAD, voice_calls


def _told(settings: VoiceSettings, *waiting: bool) -> list[LongerWait | None]:
    """The pipeline's wait after each of `waiting`, its session's `ReadBackWait`s."""
    built = voice_calls(settings)
    seen: list[LongerWait | None] = []

    async def run() -> None:
        pipeline: CallPipeline = built.calls._pipeline(
            "call-1",
            (ToneVAD(), PauseAnalyzer()),
            caller=Caller(subject="made-up"),
            consent=Consent(version=None, record_audio=False),
            language=AGENT.languages[0],
            output=capturing_output(Captured()),
        )
        for each in waiting:
            await pipeline.commands.run(ReadBackWait(waiting=each))
            seen.append(None if pipeline.longer is None else LongerWait(**vars(pipeline.longer)))

    asyncio.run(run())
    return seen


def test_the_sessions_word_turns_the_pipelines_wait_on_and_off(settings: VoiceSettings) -> None:
    longer = settings.model_copy(update={"turns": TurnSettings(read_back_silence_ms=2500)})
    assert _told(longer, True, False) == [
        LongerWait(seconds=2.5, on=True),
        LongerWait(seconds=2.5, on=False),
    ]


@pytest.mark.parametrize("waiting", [True, False])
def test_unset_the_pipeline_holds_no_wait(settings: VoiceSettings, waiting: bool) -> None:
    assert _told(settings, waiting) == [None]
