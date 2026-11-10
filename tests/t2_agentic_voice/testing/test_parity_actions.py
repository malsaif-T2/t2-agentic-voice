"""The parity of a call with an action (the design's 9.5; plan 007): one scripted call, run as a
`TextCall` and as an `AudioCall`, takes the same path through the session. The caller asks; the
model calls the action as a tool; the session reads the draft back, its summary and its closing
question; once that has played, the caller says a yes with a send word; the session says the
sending line, the write runs once, and the outcome is said. Both runs give the same turns, the
same replies (the read-back, the sending line, the outcome), the same confirmations, one write
and one outbox row, and the same `ActionCompleted`.

Both run the real parts: the library's `ChatTalker` on a `ScriptedLLM` that calls the action,
the session's read-back and confirming, the real yes rule and interruption rule, and the real
`ActionRunner` over a `MemoryOutbox`. The audio call runs the file-fed pipeline with the tests'
tone detector and a turn analyzer that ends each turn at its first pause (voice/kit.py), the
fake speech-to-text's words for each request, at real-time pace. `AudioCall` feeds one clip a
call, so the clip holds both of the caller's utterances, with a pause between them that outlasts
the turn's end, the talker and the read-back played whole."""

from __future__ import annotations

import asyncio
from functools import partial
from typing import Annotated, Any

import pytest
from pydantic import BaseModel, Field
from t2_agentic_voice.actions.action import Action, ActionContext, action
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.events import (
    ActionCompleted,
    ActionUnconfirmed,
    AgentSpeechEnded,
    CallEnded,
    ConfirmationAnswered,
    ConfirmationRequested,
    Event,
    GuardBlocked,
    Interrupted,
    ToolFinished,
    ToolStarted,
    UserTurnEnded,
)
from t2_agentic_voice.domain.action_declaration import Claims, ReadBack, Say
from t2_agentic_voice.domain.action_lines import default_action_lines
from t2_agentic_voice.domain.declaration import Language, VoiceAgent
from t2_agentic_voice.domain.ports.outbox import Outbox
from t2_agentic_voice.domain.ports.speech_to_text import AudioClip
from t2_agentic_voice.domain.yes_words import PRESET_CONSENT
from t2_agentic_voice.evals import AudioCall, ScriptedLLM, TextCall
from t2_agentic_voice.testing import audio_call
from t2_agentic_voice.voice.calls import VoiceCalls

from tests.t2_agentic_voice.fakes import FakeSpeechToText, FakeTextToSpeech, tone
from tests.t2_agentic_voice.voice.kit import PauseAnalyzer, ToneVAD

GREETING = "Welcome to the made up help desk, how can I help?"
SUMMARY = "my made up laptop will not start"
REQUEST = f"please open a request, {SUMMARY}"
# A yes with a send word, the English preset's own.
YES_SEND = f"{PRESET_CONSENT['en'].yes[0]} {PRESET_CONSENT['en'].send[1]}"
NUMBER = "4521"
READ_BACK = f"I'll open a request about: {SUMMARY}. Shall I send it?"
DONE = f"Done, your request number is {NUMBER}."
# The audio call's clip: each utterance's tone, and the pause between them, which outlasts the
# turn's end (the detector's stop and the 600 ms hold), the talker, the read-back (about 1.6 s
# of the fake's audio) and the 300 ms after it, with a second and more to spare; and the
# silence after it, for the sending line, the write and the outcome.
SPEECH_S = 0.6
PAUSE_S = 4.5
TAIL_S = 4.0
SECONDS_PER_CHAR = 0.02


class OpenRequest(BaseModel):
    summary: Annotated[str, Field(min_length=1, max_length=120)]


class RequestOpened(BaseModel):
    number: str


class Desk:
    """A made-up request desk: every write it was asked for, by its request ID."""

    def __init__(self) -> None:
        self.writes: list[tuple[str, dict[str, Any]]] = []

    def open_request_action(self) -> Action:
        @action(
            description="Open a made-up help desk request.",
            read_back=ReadBack(
                {"en": ("I'll open a request about: {summary}.", "Shall I send it?")}
            ),
            done=Say(en="Done, your request number is {number:id}."),
            claims=Claims({"en": ["opened your request"]}),
        )
        async def open_request(ctx: ActionContext, draft: OpenRequest) -> RequestOpened:
            self.writes.append((ctx.request_id, draft.model_dump()))
            return RequestOpened(number=NUMBER)

        return open_request


def _agent(desk: Desk) -> VoiceAgent:
    return VoiceAgent(
        name="parity-actions",
        languages=[Language.english(greeting=GREETING)],
        instructions="Open a request for the caller when asked.",
        tools=[desk.open_request_action()],
    )


def _model() -> ScriptedLLM:
    """The model: one request, which calls the action with the caller's summary."""
    return ScriptedLLM([ScriptedLLM.call_tool("open_request", summary=SUMMARY)])


def path(events: tuple[Event, ...] | list[Event]) -> dict[str, Any]:
    """The path a call with an action took through the session, as its public events tell it;
    each outcome's request ID left out, since every call's write draws its own."""
    (ended,) = [e for e in events if isinstance(e, CallEnded)]
    return {
        "verdicts": [(e.turn_id, e.kind, e.reason) for e in events if isinstance(e, Interrupted)],
        "turns": [(e.turn_id, e.heard) for e in events if isinstance(e, UserTurnEnded)],
        "replies": [
            (e.turn_id, e.text, e.played_fraction == 1.0)
            for e in events
            if isinstance(e, AgentSpeechEnded)
        ],
        "tools": [
            (e.turn_id, e.tool, isinstance(e, ToolFinished))
            for e in events
            if isinstance(e, ToolStarted)
        ],
        "asked": [(e.turn_id, e.action) for e in events if isinstance(e, ConfirmationRequested)],
        "answered": [
            (e.turn_id, e.action, e.decision) for e in events if isinstance(e, ConfirmationAnswered)
        ],
        "completed": [e.action for e in events if isinstance(e, ActionCompleted)],
        "unconfirmed": [e.action for e in events if isinstance(e, ActionUnconfirmed)],
        "blocked": [(e.turn_id, e.reason) for e in events if isinstance(e, GuardBlocked)],
        "records": [(t.turn_id, t.heard, t.said, t.stopped) for t in ended.report.turns],
    }


async def _rows(outbox: Outbox, events: tuple[Event, ...], desk: Desk) -> list[str]:
    """Each outbox row's state, checked to be the one write the desk did and the row the one
    `ActionCompleted` names."""
    rows = await outbox.entries()
    completed = [e.request_id for e in events if isinstance(e, ActionCompleted)]
    assert completed == [row.request_id for row in rows] == [id_ for id_, _ in desk.writes]
    return [row.state for row in rows]


def _text(settings: VoiceSettings) -> tuple[dict[str, Any], Desk, list[str]]:
    desk = Desk()
    call = TextCall(_agent(desk), llm=_model(), settings=settings)

    async def run() -> list[str]:
        async with call:
            asked = await call.user(REQUEST)
            await call.advance(10.0)  # the read-back, its summary and question, played whole
            sent = await call.user(YES_SEND)
            await call.advance(30.0)
            asked.expect.read_back(summary=SUMMARY)
            sent.expect.confirmed("open_request", summary=SUMMARY)
            sent.expect.action_ended("open_request", "done")
            sent.expect.action_completed("open_request")
            assert call.violations == ()
        return await _rows(call.outbox, tuple(call._emitted), desk)

    rows = asyncio.run(run())
    return path(call._emitted), desk, rows


def _audio(
    settings: VoiceSettings, monkeypatch: pytest.MonkeyPatch
) -> tuple[dict[str, Any], Desk, list[str], FakeSpeechToText]:
    detectors = partial(VoiceCalls, speech_detector=ToneVAD, turn_analyzer=PauseAnalyzer)
    monkeypatch.setattr(audio_call, "VoiceCalls", detectors)
    desk = Desk()
    stt = FakeSpeechToText([REQUEST, YES_SEND])
    replay = AudioCall(
        settings=settings,
        stt=stt,
        tts=FakeTextToSpeech(seconds_per_char=SECONDS_PER_CHAR),
        agent=_agent(desk),
        chat=_model(),
    )
    speech = tone(SPEECH_S, 16_000)
    clip = AudioClip(pcm16=speech + bytes(round(PAUSE_S * 16_000) * 2) + speech)

    async def run() -> list[str]:
        await replay.start()
        try:
            await replay.turn(clip, greeting=(GREETING,), language="en", lead_s=0.5, tail_s=TAIL_S)
        finally:
            await replay.aclose()
        return await _rows(replay.outbox, replay.emitted, desk)

    rows = asyncio.run(asyncio.wait_for(run(), timeout=90))
    return path(replay.emitted), desk, rows, stt


def test_a_text_turn_names_its_action_call_with_the_arguments_the_model_wrote(
    settings: VoiceSettings,
) -> None:
    """`expect.tool_call` reads the model's call of an action as it reads a tool's: by its name
    and the arguments the model wrote (testing/turn_data.py's `TextToolCall`)."""
    call = TextCall(_agent(Desk()), llm=_model(), settings=settings)

    async def run() -> None:
        async with call:
            asked = await call.user(REQUEST)
            asked.expect.tool_call("open_request", summary=SUMMARY)

    asyncio.run(run())


def test_a_call_with_an_action_takes_the_same_path_as_text_and_as_audio(
    settings: VoiceSettings, monkeypatch: pytest.MonkeyPatch
) -> None:
    text, text_desk, text_rows = _text(settings)
    audio, audio_desk, audio_rows, stt = _audio(settings, monkeypatch)
    assert len(stt.calls) == 2  # one request for each of the caller's turns
    assert text == audio
    assert text["turns"] == [(0, REQUEST), (1, YES_SEND)]
    assert text["verdicts"] == [] and text["blocked"] == []
    (greeting, read_back, sending, outcome) = text["replies"]
    assert greeting == (None, GREETING, True)
    assert read_back == (0, READ_BACK, True)  # the summary and the question, played whole
    assert sending == (1, default_action_lines("en").sending, True)  # the library's line
    assert outcome == (None, DONE, True)  # the outcome, answering no turn
    assert text["asked"] == [(0, "open_request")]
    assert text["answered"] == [(1, "open_request", "yes")]
    assert text["completed"] == ["open_request"] and text["unconfirmed"] == []
    assert text_desk.writes[0][1] == audio_desk.writes[0][1] == {"summary": SUMMARY}
    assert text_rows == audio_rows == ["done"]
