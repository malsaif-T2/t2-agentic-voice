"""The session's word to the Pipecat side of a read-back awaiting its answer
(voice/session/read_back_wait.py; plan 010's 1.11, Q9): with `turns.read_back_silence_ms` set,
`ReadBackWait` on as the call starts confirming and off as it ends, once each; unset, never,
so a call's commands are as they were. The yes rule and the port are the tests' fakes
(yes_support.py)."""

from __future__ import annotations

import asyncio

from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.settings.turns import TurnSettings
from t2_agentic_voice.voice.session.commands import ReadBackWait

from tests.t2_agentic_voice.session_fakes import FakeSessionIO
from tests.t2_agentic_voice.voice.session.read_back_support import asked, read_whole
from tests.t2_agentic_voice.voice.session.talker_support import settle, talked
from tests.t2_agentic_voice.voice.session.yes_support import FakeJobs, FakeYesRule, confirm_call

YES = "made-up-yes"  # a yes word alone, after the closing question


def _waits(io: FakeSessionIO) -> list[bool]:
    return [command.waiting for command in io.commands.of(ReadBackWait)]


def _confirmed(settings: VoiceSettings) -> list[list[bool]]:
    """The waits told once the read-back is asked for, once it has played, and once a yes
    ended confirming."""
    io, _, _ = confirm_call(settings, FakeJobs())
    seen: list[list[bool]] = []

    async def drive() -> None:
        await asked(io)
        seen.append(_waits(io))
        await read_whole(io)
        await settle()
        await io.clock.advance(1.0)
        seen.append(_waits(io))
        await talked(io, 1, YES)
        seen.append(_waits(io))
        await io.ending()
        await io.close()

    asyncio.run(drive())
    return seen


def test_the_wait_is_told_on_as_confirming_starts_and_off_as_a_yes_ends_it(
    settings: VoiceSettings, yes_rule: FakeYesRule
) -> None:
    longer = settings.model_copy(update={"turns": TurnSettings(read_back_silence_ms=3000)})
    assert _confirmed(longer) == [[True], [True], [True, False]]


def test_unset_no_wait_is_ever_told(settings: VoiceSettings, yes_rule: FakeYesRule) -> None:
    """A characterization of the default (GP-18): no new command reaches a call."""
    assert settings.turns.read_back_silence_ms is None
    assert _confirmed(settings) == [[], [], []]
