"""voice's entry point and the talker (voice/calls.py, voice/talkers.py; plan 006): each call of an
agent that runs the talker gets the talker its factory builds for it, on the call's clock, in
its `CallSetup`, and its speech-to-text bridge sends the early start's `held` requests; a call of
the echo gets neither. A call the dev console chose a speech-to-text for (`ChosenStt`) is heard
by it, with its settings; every other call by the runtime's."""

from __future__ import annotations

from typing import Any

from t2_agentic_voice.agent.talker import TalkerCall
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.identity import Caller, Consent
from t2_agentic_voice.core.settings.stt import SttSettings
from t2_agentic_voice.core.tracing import Tracing
from t2_agentic_voice.domain.declaration import Language, VoiceAgent
from t2_agentic_voice.testing.llm_fakes import ScriptedLLM
from t2_agentic_voice.voice.calls import ChosenStt, VoiceCalls
from t2_agentic_voice.voice.file_transport import file_output

from tests.t2_agentic_voice.fakes import FakeClock, FakePhrases, FakeSpeechToText, FakeTextToSpeech
from tests.t2_agentic_voice.session_fakes import AGENT as ECHO
from tests.t2_agentic_voice.voice.kit import ToneVAD

AGENT = VoiceAgent(
    name="talker", languages=[Language.english(greeting="Hello.")], instructions="Be brief."
)
CALLER, CONSENT = Caller(subject="made-up"), Consent(version=None, record_audio=False)


def _calls(settings: VoiceSettings, agent: VoiceAgent, **given: Any) -> VoiceCalls:
    return VoiceCalls(
        agent=agent,
        settings=settings,
        stt=FakeSpeechToText(),
        tts=FakeTextToSpeech(),
        phrases=FakePhrases.of(agent),
        tracing=Tracing(),
        emit=lambda event: None,
        **given,
    )


def test_each_call_of_the_talker_gets_its_own_and_the_early_start(
    settings: VoiceSettings,
) -> None:
    built: list[tuple[TalkerCall, object]] = []
    clock = FakeClock()

    def factory(call: TalkerCall, on: object) -> Any:
        built.append((call, on))
        return object()

    chat = ScriptedLLM([])
    calls = _calls(settings, AGENT, talker=factory, chat=chat, clock=clock)
    language = AGENT.languages[0]
    pipeline = calls._pipeline(
        "call-7",
        (ToneVAD(), None),
        caller=CALLER,
        consent=CONSENT,
        language=language,
        output=file_output(),
    )
    ((call, on),) = built
    assert (call, on) == (TalkerCall(call_id="call-7", caller=CALLER, language="en"), clock)
    assert pipeline.setup.talker is not None and pipeline.stt_bridge._early
    assert pipeline.setup.overlap_model is chat  # for an agent that asks about uncertain overlaps
    echo = _calls(settings, ECHO, chat=chat)._pipeline(
        "call-8",
        (ToneVAD(), None),
        caller=CALLER,
        consent=CONSENT,
        language=ECHO.languages[0],
        output=file_output(),
    )
    assert echo.setup.talker is None and not echo.stt_bridge._early
    assert echo.setup.overlap_model is None


def test_each_call_gets_the_one_action_jobs_the_runtime_was_given(
    settings: VoiceSettings,
) -> None:
    """Plan 007: one `ActionJobs` for every call, which tells them apart by the call's ID, on
    each call's `CallSetup`; with none, no call has one (its confirmed yes is then told as the
    `error` notice, and nothing is sent: yes_turns.py)."""
    jobs = object()
    calls = _calls(settings, AGENT, talker=lambda call, on: object(), action_jobs=jobs)
    built = [
        calls._pipeline(
            call_id,
            (ToneVAD(), None),
            caller=CALLER,
            consent=CONSENT,
            language=AGENT.languages[0],
            output=file_output(),
        )
        for call_id in ("call-1", "call-2")
    ]
    assert [pipeline.setup.action_jobs for pipeline in built] == [jobs, jobs]
    unwired = _calls(settings, AGENT, talker=lambda call, on: object())._pipeline(
        "call-3",
        (ToneVAD(), None),
        caller=CALLER,
        consent=CONSENT,
        language=AGENT.languages[0],
        output=file_output(),
    )
    assert unwired.setup.action_jobs is None


def test_a_call_with_a_chosen_speech_to_text_is_heard_by_it_and_no_other_call_is(
    settings: VoiceSettings,
) -> None:
    chosen_stt = FakeSpeechToText()
    chosen_settings = settings.model_copy(
        update={"stt": SttSettings(model="whisper-large-v3-turbo", live_language="auto")}
    )
    asked: list[str] = []

    def chosen(call_id: str) -> ChosenStt | None:
        asked.append(call_id)
        return ChosenStt(chosen_stt, chosen_settings) if call_id == "chosen" else None

    calls = _calls(settings, ECHO, chosen=chosen)

    def pipeline(call_id: str) -> Any:
        return calls._pipeline(
            call_id,
            (ToneVAD(), None),
            caller=CALLER,
            consent=CONSENT,
            language=ECHO.languages[0],
            output=file_output(),
        )

    one, other = pipeline("chosen"), pipeline("other")
    assert asked == ["chosen", "other"]
    assert one.stt_bridge._requests._stt is chosen_stt and one.setup.settings is chosen_settings
    assert other.stt_bridge._requests._stt is calls._stt and other.setup.settings is settings
    default = _calls(settings, ECHO)  # no lookup given: every call the runtime's (GP-18)
    alone = default._pipeline(
        "alone",
        (ToneVAD(), None),
        caller=CALLER,
        consent=CONSENT,
        language=ECHO.languages[0],
        output=file_output(),
    )
    assert alone.stt_bridge._requests._stt is default._stt and alone.setup.settings is settings
