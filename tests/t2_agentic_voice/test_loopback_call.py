"""Plan 003's step 16, the integration check with no spend: one call as a browser makes it, from its
join to its end, through the runtime's router (api/router.py), the real pipeline
(voice/pipeline.py) and the echo session (voice/session/), the providers fakes and the audio
generated (no audio file: tests/ole5_voice/evals/test_no_audio.py). What it shares with plan
005's check is loopback_support.py's.

A local aiortc peer, built with `RTCConfiguration(iceServers=[])` (tests/conftest.py makes
aiortc's default list raise), plays the browser's part as `t2v-client.js` does: it joins the
minimal example's echo agent (`DevIdentity`, `env` dev, from loopback), offers, sends its
candidates once the offer is answered and then their end, says hello on the data channel, waits
out the greeting, and sends a sine that the fake speech detector hears as speech. The fake
speech-to-text hears made-up words, the session says them back, and the client hears the echo
from the fake text-to-speech, which says the heard words at a pitch of their own; then it hangs
up. It also checks what the tracks left to this test: the phrase cache, real and declared at
the runtime's start under the test's folder, gets no new file and is never asked for the heard
words (invariant 8); and no public event, and no session message that names a thing, is sent
twice. The call runs on a selector loop, as `serve()` runs it (api/server.py), every wait
bounded, every peer closed and no task left.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path

import httpx
import pytest
from minimal_example.app import agent
from t2_agentic_voice.adapters.phrase_cache import PhraseCache
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.events import CallEnded
from t2_agentic_voice.core.settings.storage import StorageSettings
from t2_agentic_voice.core.settings.tts import LanguageTag
from t2_agentic_voice.domain.ports.text_to_speech import AudioChunk
from t2_agentic_voice.voice.protocol import RESERVED_TYPES, SESSION_MESSAGES
from t2_agentic_voice.voice.session.report import REPORTS

from tests.t2_agentic_voice.fakes import FakeSpeechToText
from tests.t2_agentic_voice.loopback_audio import (
    HEARD_HZ,
    PHRASE_HZ,
    SECONDS_PER_CHAR,
    PitchedSpeech,
)
from tests.t2_agentic_voice.loopback_support import (
    ENGLISH,
    WAIT_S,
    Browser,
    echo_runtime,
    files,
    run_call,
)
from tests.t2_agentic_voice.voice.kit import until

# The made-up words the fake speech-to-text hears, said back at a pitch of their own.
HEARD = "a loopback call said back"
# How long the caller speaks.
SPEECH_S = 0.6
# How far each pitch's audio, as heard, may be from what was said: Opus's frame edges and the
# output's 40 ms chunks (the agent's bound).
TOLERANCE_S = 0.15


async def talk(browser: Browser) -> None:
    """Wait out the greeting, speak, hear the echo's words, and hang up once they have
    played."""
    await browser.greeted()
    spoke = len(browser.states())
    browser.signal.say(SPEECH_S)
    await until(lambda: "speaking" in browser.states()[spoke:], timeout=WAIT_S)
    await until(lambda: browser.states()[-1] == "listening", timeout=WAIT_S)
    echo_s = len(HEARD) * SECONDS_PER_CHAR
    await until(lambda: browser.heard_s(HEARD_HZ) >= echo_s - TOLERANCE_S, timeout=WAIT_S)
    await browser.hang_up()


def test_a_browser_like_peer_joins_speaks_and_hears_its_words_said_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = VoiceSettings(env="dev", storage=StorageSettings(var_dir=tmp_path / "var"))
    stt, tts = FakeSpeechToText([HEARD]), PitchedSpeech([HEARD])
    app, emitted = echo_runtime(settings, stt, tts)
    asked: list[str] = []
    audio = PhraseCache.audio

    def asking(cache: PhraseCache, text: str, *, language: LanguageTag) -> AudioChunk:
        asked.append(text)
        return audio(cache, text, language=language)

    monkeypatch.setattr(PhraseCache, "audio", asking)
    folder = settings.storage.var_dir / agent.name / "phrases"
    declared: list[str] = []

    async def steps(browser: Browser, http: httpx.AsyncClient) -> None:
        declared.extend(files(folder))
        await browser.connect(http)
        await talk(browser)

    browser, left = run_call(app, steps)
    assert not left, left
    assert browser.peer.connectionState == "closed"

    # Its candidates went once the offer was answered, then their end, each answered.
    assert len(browser.patches) >= 2
    # The echo's words came back from the fake text-to-speech, once; the phrases from the cache.
    echo_s, phrases_s = len(HEARD), len(ENGLISH.greeting) + len(ENGLISH.echo_frame)
    assert abs(browser.heard_s(HEARD_HZ) - echo_s * SECONDS_PER_CHAR) <= TOLERANCE_S
    assert abs(browser.heard_s(PHRASE_HZ) - phrases_s * SECONDS_PER_CHAR) <= 2 * TOLERANCE_S
    assert [text for text, _ in tts.calls].count(HEARD) == 1 and len(stt.calls) == 1

    # The phrase cache, declared at the start, got no new file and was never asked for the
    # heard words, but for the greeting and the frame (invariant 8).
    assert declared and files(folder) == declared
    assert HEARD not in asked and {ENGLISH.greeting, ENGLISH.echo_frame} <= set(asked)

    # Every message is t2v/1's, or SmallWebRTC's own `peerLeft` as the call ends, which the
    # client ignores; none that names a thing came twice.
    kinds = {kind.model_fields["type"].default for kind in SESSION_MESSAGES}
    for message in browser.messages:
        ours = message.get("v") == 1 and message["type"] in kinds
        assert ours or (message["type"] in RESERVED_TYPES and "v" not in message), message
    assert [m["reason"] for m in browser.of("ended")] == ["hangup"]
    captions = [
        (m["speaker"], m["turn_id"], m["reply_id"], m["clause"], m["text"])
        for m in browser.of("caption")
    ]
    assert captions == [
        ("agent", None, 0, 0, ENGLISH.greeting),
        ("caller", 0, None, None, HEARD),
        ("agent", 0, 1, 0, ENGLISH.echo_frame),
        ("agent", 0, 1, 1, HEARD),
    ]

    # No public event came twice: each the call sent, once.
    sent = Counter((type(event).__name__, event.turn_id) for event in emitted)
    assert sent == Counter(
        [
            ("CallStarted", None),
            ("AgentSpeechEnded", None),
            ("UserTurnEnded", 0),
            ("AgentSpeechEnded", 0),
            ("TurnMetrics", 0),
            ("CallEnded", None),
        ]
    )
    (ended,) = [event for event in emitted if isinstance(event, CallEnded)]
    report = ended.report
    assert [m["call_id"] for m in browser.of("hello")] == [report.call_id]
    assert report.ended_by == "hangup" and report.client is not None
    assert report.client.candidate_type == "host"
    (turn,) = report.turns
    assert (turn.heard, turn.said, turn.dropped) == (HEARD, f"{ENGLISH.echo_frame} {HEARD}", False)
    usage = {each.model: each for each in report.usage}
    tts_usage = usage[settings.tts.languages["en"].model]
    assert (tts_usage.requests, tts_usage.cache_hits) == (1, 2)
    written = (settings.storage.var_dir / REPORTS / f"{report.call_id}.json").read_text("utf-8")
    assert HEARD not in written
