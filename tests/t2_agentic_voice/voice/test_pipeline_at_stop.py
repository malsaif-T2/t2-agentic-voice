"""The held request at the detector's stop in a call's pipeline (voice/pipeline.py, turns.py's
`stops_early`; plan 010's 2.2): the speech-to-text bridge sends it there only in a call with a
talker, with `turns.early_at_stop` on and Smart Turn's verdict held; an echo call, a call with
Smart Turn off and one with the setting off (the default) send it at the verdict, as before."""

from __future__ import annotations

import pytest
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.settings.turns import TurnSettings
from t2_agentic_voice.testing.llm_fakes import ScriptedLLM
from t2_agentic_voice.voice.file_transport import file_output

from tests.t2_agentic_voice.session_fakes import AGENT as ECHO
from tests.t2_agentic_voice.voice.kit import PauseAnalyzer, ToneVAD
from tests.t2_agentic_voice.voice.test_calls_talker import AGENT, CALLER, CONSENT, _calls


@pytest.mark.parametrize(
    ("talker", "on", "smart_turn", "at_stop"),
    [
        (True, True, True, True),
        (True, False, True, False),
        (True, True, False, False),
        (False, True, True, False),
    ],
    ids=["on", "off by default", "no smart turn", "an echo call"],
)
def test_the_bridge_sends_at_the_stop_only_for_the_talker_with_the_setting_on(
    settings: VoiceSettings, talker: bool, on: bool, smart_turn: bool, at_stop: bool
) -> None:
    turns = TurnSettings(early_at_stop=True) if on else TurnSettings()
    given = settings.model_copy(update={"turns": turns})
    agent = AGENT if talker else ECHO
    calls = _calls(given, agent, talker=lambda call, on: object(), chat=ScriptedLLM([]))
    pipeline = calls._pipeline(
        "call-1",
        (ToneVAD(), PauseAnalyzer() if smart_turn else None),
        caller=CALLER,
        consent=CONSENT,
        language=agent.languages[0],
        output=file_output(),
    )
    assert pipeline.stt_bridge._holds.at_stop is at_stop
