"""The warm requests a call sends as it joins (voice/join_warmth.py; TD-089), by default and under
`warmup.at_join`, with fake providers that count each request, and a call answered through
`VoiceCalls` with a local aiortc peer as the browser, whose server steps are logged as times
alone. Nothing leaves the machine."""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import AsyncIterator

import pytest
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.errors import ProviderError
from t2_agentic_voice.core.identity import Caller, Consent
from t2_agentic_voice.core.logging import FIELDS
from t2_agentic_voice.core.settings.warmup import WarmupSettings
from t2_agentic_voice.domain.ports.chat_model import ChatEvent, ChatRequest
from t2_agentic_voice.voice import join_warmth
from t2_agentic_voice.voice.join_warmth import JoinWarmth

from tests.t2_agentic_voice.fakes import FAKE_FLOW, FakeSpeechToText, FakeTextToSpeech
from tests.t2_agentic_voice.session_fakes import AGENT
from tests.t2_agentic_voice.voice.kit import client_answered, client_offer, until, voice_calls

CALLER, CONSENT = Caller(subject="made-up"), Consent(version=None, record_audio=False)
ENGLISH = AGENT.languages[0]


class _WarmingStt(FakeSpeechToText):
    """The fakes' speech-to-text with a `warm_up` that counts, fails or hangs."""

    def __init__(self, *, failure: Exception | None = None, hang: bool = False) -> None:
        super().__init__()
        self.warmed = 0
        self.failure, self.hang = failure, hang

    async def warm_up(self) -> None:
        self.warmed += 1
        if self.hang:
            await asyncio.Event().wait()
        if self.failure is not None:
            raise self.failure


class _Chat:
    """A chat model whose connection is `warm` or not, its warm requests counted."""

    name, data_flow = "fake-chat", FAKE_FLOW

    def __init__(self, *, warm: bool) -> None:
        self.is_warm, self.warmed = warm, 0

    def warm(self) -> bool:
        return self.is_warm

    async def warm_up(self) -> None:
        self.warmed += 1

    def stream(self, request: ChatRequest) -> AsyncIterator[ChatEvent]:
        raise AssertionError("a warm request never streams")

    async def aclose(self) -> None:
        pass


def _warmed(caplog: pytest.LogCaptureFixture) -> dict[str, dict[str, object]]:
    lines = [r for r in caplog.records if r.getMessage() == "call_warmed"]
    return {getattr(r, FIELDS)["target"]: getattr(r, FIELDS) for r in lines}


def test_the_join_warm_up_and_the_reopen_are_off_by_default(settings: VoiceSettings) -> None:
    """GP-18's characterization of the default: no join sends a warm request."""
    assert WarmupSettings().at_join is False and settings.warmup.at_join is False
    assert WarmupSettings().after_cancel is False and settings.warmup.after_cancel is False
    stt, tts, chat = _WarmingStt(), FakeTextToSpeech(), _Chat(warm=False)

    async def run() -> None:
        warmth = JoinWarmth(on=settings.warmup.at_join, tts=tts, chat=chat)
        warmth.joined("call-1", stt, "en")
        await asyncio.sleep(0.05)
        await warmth.aclose()

    asyncio.run(run())
    assert (stt.warmed, tts.checked, chat.warmed) == (0, [], 0)


def test_a_join_sends_each_warm_request_once_in_the_background(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO)
    stt, tts, chat = _WarmingStt(), FakeTextToSpeech(), _Chat(warm=False)

    async def run() -> None:
        warmth = JoinWarmth(on=True, tts=tts, chat=chat)
        warmth.joined("call-1", stt, "ar-SA")
        await until(lambda: len(_warmed(caplog)) == 3)
        await warmth.aclose()

    asyncio.run(run())
    assert (stt.warmed, tts.checked, chat.warmed) == (1, ["ar-SA"], 1)
    lines = _warmed(caplog)
    assert {target: line["outcome"] for target, line in lines.items()} == {
        "stt": "warm",
        "tts": "warm",
        "chat": "warm",
    }
    assert lines["chat"]["provider"] == "fake-chat"
    assert set(lines["stt"]) == {"call_id", "target", "provider", "ms", "outcome", "error"}


def test_a_chosen_calls_own_voice_and_chat_are_warmed_in_place_of_the_runtimes() -> None:
    """A call whose page chose its voice and model warms those, never the runtime's."""
    tts, chat = FakeTextToSpeech(), _Chat(warm=False)
    chosen_tts, chosen_chat = FakeTextToSpeech(), _Chat(warm=False)

    async def run() -> None:
        warmth = JoinWarmth(on=True, tts=tts, chat=chat)
        warmth.joined("call-1", FakeSpeechToText(), "en", tts=chosen_tts, chat=chosen_chat)
        await until(lambda: chosen_tts.checked == ["en"] and chosen_chat.warmed == 1)
        await warmth.aclose()

    asyncio.run(run())
    assert (tts.checked, chat.warmed) == ([], 0)


def test_a_warm_chat_connection_is_sent_no_request_and_a_provider_without_one_none() -> None:
    stt, tts, chat = FakeSpeechToText(), FakeTextToSpeech(), _Chat(warm=True)

    async def run() -> None:
        warmth = JoinWarmth(on=True, tts=tts, chat=chat)
        warmth.joined("call-1", stt, "en")
        await until(lambda: tts.checked == ["en"])
        await warmth.aclose()

    asyncio.run(run())
    assert chat.warmed == 0 and stt.calls == []


def test_a_failed_warm_request_is_logged_by_its_kind_and_never_fails_the_call(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.INFO)
    failure = ProviderError("rejected", False, details={"error": "secret detail 4471"})
    stt = _WarmingStt(failure=failure)
    tts = FakeTextToSpeech(languages=("ar",))  # no voice for English: its check raises

    async def run() -> None:
        warmth = JoinWarmth(on=True, tts=tts, chat=None)
        warmth.joined("call-1", stt, "en")
        await until(lambda: len(_warmed(caplog)) == 2)
        await warmth.aclose()

    asyncio.run(run())
    lines = _warmed(caplog)
    assert (lines["stt"]["outcome"], lines["stt"]["error"]) == ("failed", "rejected")
    assert lines["tts"]["outcome"] == "failed"
    assert "secret detail" not in caplog.text


def test_a_warm_request_past_its_bound_ends_and_the_close_cancels_one_in_flight(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)
    monkeypatch.setattr(join_warmth, "WARM_TIMEOUT_S", 0.05)
    timed_out, held = _WarmingStt(hang=True), _WarmingStt(hang=True)

    async def run() -> None:
        warmth = JoinWarmth(on=True, tts=FakeTextToSpeech(), chat=None)
        warmth.joined("call-1", timed_out, "en")
        await until(lambda: "stt" in _warmed(caplog))
        monkeypatch.setattr(join_warmth, "WARM_TIMEOUT_S", 60.0)
        warmth.joined("call-2", held, "en")
        await until(lambda: held.warmed == 1)
        await asyncio.wait_for(warmth.aclose(), timeout=1)

    asyncio.run(run())
    assert _warmed(caplog)["stt"]["error"] == "TimeoutError"


def test_an_answered_call_warms_its_providers_once_and_logs_its_steps_with_no_address(
    settings: VoiceSettings, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.INFO)
    stt = _WarmingStt()
    built = voice_calls(
        settings.model_copy(update={"warmup": WarmupSettings(at_join=True)}), stt=stt
    )
    addresses: list[str] = []

    async def run() -> None:
        await built.calls.start()
        peer, _, offer = await client_offer()
        addresses.extend(re.findall(r"a=candidate:\S+ \d \S+ \d+ (\S+)", offer))
        try:
            answer = await built.calls.answer(
                "call-1", offer, caller=CALLER, consent=CONSENT, language=ENGLISH
            )
            await client_answered(peer, answer)
            await until(lambda: built.calls.phase("call-1") == "connected")
            await until(lambda: len(_warmed(caplog)) == 2)
        finally:
            await peer.close()
            await built.calls.aclose()

    asyncio.run(asyncio.wait_for(run(), timeout=60), loop_factory=asyncio.SelectorEventLoop)
    assert (stt.warmed, built.tts.checked) == (1, ["en"])
    steps = [r for r in caplog.records if r.getMessage() in {"call_answered", "call_connected"}]
    fields = {r.getMessage(): getattr(r, FIELDS) for r in steps}
    assert set(fields["call_answered"]) == {"call_id", "detectors_ms", "peer_ms", "pipeline_ms"}
    assert set(fields["call_connected"]) == {"call_id", "offer_to_connected_ms"}
    assert addresses
    for line in fields.values():
        assert all(isinstance(value, float) for key, value in line.items() if key != "call_id")
        assert not any(address in str(line) for address in addresses)
