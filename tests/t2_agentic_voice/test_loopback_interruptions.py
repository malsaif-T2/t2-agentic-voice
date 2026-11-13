"""Plan 005's step 9, the integration check with no spend of its five tracks merged: the caller
speaking over a long reply, in a call as a browser makes it, under `interruptions.mode =
"two_step"`, through the runtime's router, the real pipeline and bridges, the real session and
the real rule of domain/interruptions.py; the speech detector, the turn analyzer, speech-to-text
and text-to-speech are the fakes', the audio generated (no audio file:
tests/ole5_voice/evals/test_no_audio.py), and no request goes to Groq. What it shares with plan
003's check (test_loopback_call.py) is loopback_support.py's (TD-087); how it watches the server
side, loopback_watch.py's.

In each call the client waits out the greeting and speaks; the fake speech-to-text hears `LONG`,
made-up words the echo says back as a long reply, from the fake text-to-speech at a pitch of its
own. Once the client has heard OVER_AT_S of it, it speaks over it, and the fake speech-to-text
hears, in each request of that overlap (its window and its whole overlap), a word of the English
preset's lists (domain/words.py's `PRESET_WORDS`), never an item's text:

- a stop word brings `duck` on the data channel, then the session's `StopSpeaking`, then
  `unduck`; the stop goes straight to the output transport, as Pipecat's one interruption from
  the session bridge; once it is there, at most the one 40 ms chunk already in its WebRTC track
  leaves (io.py's stop path), and the client hears nothing more of the reply;
- a listening sound brings `duck`, then `unduck`, and the reply plays to its end;
- both, one after the other: no Pipecat interruption fires but the session's, one for its one
  stop (Pipecat's own stay off: D-018's answer 8).

The client's volume handling (`t2v-client.js`: `duck` lowers the agent's playback, `unduck`
restores it) is checked as far as a Python test can: the messages it acts on, in order, and when
they came against the agent's audio as the client played it; the page is checked in a browser.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from pathlib import Path

import httpx
import pytest
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.events import AgentSpeechEnded, Event, Interrupted, UserTurnEnded
from t2_agentic_voice.core.settings.interruptions import InterruptionSettings
from t2_agentic_voice.core.settings.storage import StorageSettings
from t2_agentic_voice.domain.ports.speech_to_text import AudioClip, Transcript
from t2_agentic_voice.domain.words import PRESET_WORDS
from t2_agentic_voice.voice.transport import OUT_CHUNK_10MS

from tests.t2_agentic_voice.fakes import FakeSpeechToText
from tests.t2_agentic_voice.loopback_audio import HEARD_HZ, SECONDS_PER_CHAR, PitchedSpeech
from tests.t2_agentic_voice.loopback_support import WAIT_S, Browser, echo_runtime, run_call
from tests.t2_agentic_voice.loopback_watch import watch
from tests.t2_agentic_voice.voice.kit import until

WORDS = PRESET_WORDS["en"]
STOP, LISTENING = WORDS.stop[0], WORDS.backchannel[0]
# The caller's first turn, said back as the long reply: made-up words, none of the English
# preset's lists, about 4 s at the fakes' pace.
LONG = (
    "this long reply of the loopback check keeps playing for a few seconds so that the "
    "caller has time to speak over it while the agent talks"
)
REPLY_S = len(LONG) * SECONDS_PER_CHAR
# How long the caller speaks each time; how much of the reply it hears before it speaks over it;
# how long it listens after a stop, so the reply's audio would show if it went on.
SPEECH_S, OVER_AT_S, AFTER_STOP_S = 0.6, 0.6, 1.0
# How far the reply's audio, as heard, may be from its length (test_loopback_call.py's).
TOLERANCE_S = 0.15
# How much more of the reply the client may hear than the track gave by the time the stop
# reached the output: the one output chunk then in the WebRTC track (40 ms), and an Opus packet
# (20 ms) at each end of the reply, since the client hears whole packets. The stop path's times
# (3 to 7 ms to the output, 33 to 74 ms to the client, measured) are kept as the test's
# properties, not held to a bound: a machine under load stretches them all alike.
OPUS_PACKET_S = 0.02
AFTER_REACHED_S = OUT_CHUNK_10MS / 100 + 2 * OPUS_PACKET_S


class Hears(FakeSpeechToText):
    """The fakes' speech-to-text, hearing `now` in every request: the test sets it before the
    caller speaks."""

    def __init__(self) -> None:
        super().__init__()
        self.now = ""

    async def transcribe(
        self, clip: AudioClip, *, language: str | None, prompt: str | None
    ) -> Transcript:
        self.calls.append((clip, language, prompt))
        return Transcript(text=self.now, language=language, billed_seconds=max(10.0, clip.seconds))


def two_step(tmp_path: Path) -> VoiceSettings:
    return VoiceSettings(
        env="dev",
        storage=StorageSettings(var_dir=tmp_path / "var"),
        interruptions=InterruptionSettings(mode="two_step"),
    )


async def over_the_reply(browser: Browser, stt: Hears, said: str) -> None:
    """Wait out the greeting, speak, and hear LONG said back; once OVER_AT_S of it has played,
    speak over it, the fake hearing `said`."""
    await browser.greeted()
    stt.now = LONG
    browser.signal.say(SPEECH_S)
    await until(lambda: browser.heard_s(HEARD_HZ) >= OVER_AT_S, timeout=WAIT_S)
    stt.now = said
    browser.signal.say(SPEECH_S)


def of[E: Event](emitted: list[Event], kind: type[E]) -> list[E]:
    return [event for event in emitted if isinstance(event, kind)]


def turns_ended(emitted: list[Event], count: int) -> Callable[[], bool]:
    """Whether `count` of the caller's turns have ended, so none is left open at the hang-up."""
    return lambda: len(of(emitted, UserTurnEnded)) >= count


def test_a_stop_word_over_the_reply_ducks_stops_it_at_once_and_unducks(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, record_property: Callable[[str, object], None]
) -> None:
    """Its times, in ms after the session's `StopSpeaking`, are kept as the test's properties
    (`--junitxml`): the stop reaching the output, the last 10 ms of the reply leaving its track,
    the last packet of it reaching the client, and the client's track giving it."""
    settings = two_step(tmp_path)
    stt, tts, watched = Hears(), PitchedSpeech([LONG]), watch(monkeypatch)
    app, emitted = echo_runtime(settings, stt, tts)

    async def steps(browser: Browser, http: httpx.AsyncClient) -> None:
        await browser.connect(http)
        await over_the_reply(browser, stt, STOP)
        await until(lambda: bool(browser.of("unduck")), timeout=WAIT_S)
        await until(lambda: browser.states()[-1] == "listening", timeout=WAIT_S)
        await until(turns_ended(emitted, 2), timeout=WAIT_S)
        await asyncio.sleep(AFTER_STOP_S)
        await browser.hang_up()

    browser, left = run_call(app, steps)
    assert not left, left
    assert browser.peer.connectionState == "closed"

    # The session lowered the agent's voice, asked for the overlap's parts, stopped the reply on
    # the stop word, then brought its voice back; the client got `duck` before the stop, and
    # `unduck` after it, then the clause playing marked cut.
    assert watched.named() == ["duck", "HearOverlap", "StopSpeaking", "unduck"]
    (stopped,) = watched.stops()
    (duck,), (unduck,) = browser.of("duck"), browser.of("unduck")
    assert duck["level"] == settings.interruptions.duck_level
    assert browser.came("duck")[0] < stopped < browser.came("unduck")[0]
    cut = browser.of("caption")[-1]
    assert (cut["reply_id"], cut["clause"], cut["text"], cut["cut"]) == (1, 1, LONG, True)
    assert browser.messages.index(unduck) < browser.messages.index(cut)

    # The stop went straight to the output transport, at once: Pipecat's one interruption,
    # broadcast by the session bridge in the session's own `StopSpeaking` step, its frames made
    # once the stop was given and handled by the output after, waiting on nothing the call
    # controls. From then, at most the one chunk already in its WebRTC track left (40 ms), and
    # the client heard nothing more of the reply: the rest of it never came.
    (reached,) = watched.reached
    last = [frame for frame in browser.heard if frame.hz is not None][-1]
    times = {
        "reached": reached,
        "sent": max(at for at, hz in watched.sent if hz is not None),
        "arrived": browser.arrived(last),
        "played": last.at,
    }
    for name, at in times.items():
        record_property(f"{name}_ms", round((at - stopped) * 1000, 1))
    assert watched.broadcasts == ["t2v-session-bridge"]
    made = watched.interruptions
    assert made and all(stopped <= at <= reached for at in made)
    assert len(watched.loud_after(reached)) <= OUT_CHUNK_10MS
    heard_s = browser.heard_s(HEARD_HZ)
    assert heard_s <= watched.given_s(HEARD_HZ, by=reached) + AFTER_REACHED_S
    assert OVER_AT_S <= heard_s <= REPLY_S - AFTER_STOP_S

    # One interruption, a stop word's, of the reply that answered turn 0; at most two requests
    # decided the overlap, and the stop word was never said back.
    assert [(e.turn_id, e.kind, e.reason) for e in of(emitted, Interrupted)] == [
        (0, "stop", "stop_word")
    ]
    assert len(stt.calls) - 1 <= 2 and [text for text, _ in tts.calls].count(LONG) == 1
    assert STOP not in [text for text, _ in tts.calls]


def test_a_listening_sound_over_the_reply_ducks_and_unducks_and_it_plays_to_its_end(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings = two_step(tmp_path)
    stt, tts, watched = Hears(), PitchedSpeech([LONG]), watch(monkeypatch)
    app, emitted = echo_runtime(settings, stt, tts)

    async def steps(browser: Browser, http: httpx.AsyncClient) -> None:
        await browser.connect(http)
        await over_the_reply(browser, stt, LISTENING)
        await until(lambda: bool(browser.of("unduck")), timeout=WAIT_S)
        played = REPLY_S - TOLERANCE_S
        await until(lambda: browser.heard_s(HEARD_HZ) >= played, timeout=WAIT_S)
        await until(lambda: browser.states()[-1] == "listening", timeout=WAIT_S)
        await until(turns_ended(emitted, 2), timeout=WAIT_S)
        await browser.hang_up()

    browser, left = run_call(app, steps)
    assert not left, left

    # `duck`, then `unduck` once the overlap was decided, with nothing between them that brings
    # the volume back (a new reply's caption); no stop, so no interruption of any kind.
    assert watched.named() == ["duck", "HearOverlap", "unduck"]
    assert watched.stops() == [] and watched.interruptions == [] and watched.broadcasts == []
    (duck_at,), (unduck_at,) = browser.came("duck"), browser.came("unduck")
    between = [m for at, m in browser.received() if duck_at < at < unduck_at]
    assert not [m for m in between if m.get("type") == "caption"]
    assert not [m for m in browser.of("caption") if m["cut"]]

    # The reply played to its end: the client played some of it lowered, between `duck` and
    # `unduck`, and the rest at full volume after.
    loud = [frame for frame in browser.heard if frame.hz is not None]
    assert [frame for frame in loud if duck_at < frame.at < unduck_at]
    assert [frame for frame in loud if frame.at > unduck_at]
    assert abs(browser.heard_s(HEARD_HZ) - REPLY_S) <= TOLERANCE_S
    (reply,) = [e for e in of(emitted, AgentSpeechEnded) if e.turn_id == 0]
    assert reply.played_fraction == 1.0

    # The rule let the reply go on, a listening sound's verdict; the turn was not answered, and
    # its window and its whole overlap were the only requests that decided it.
    assert [(e.turn_id, e.kind, e.reason) for e in of(emitted, Interrupted)] == [
        (0, "false", "listening")
    ]
    assert [m["turn_id"] for m in browser.of("caption") if m["speaker"] == "caller"] == [0]
    assert [text for text, _ in tts.calls].count(LONG) == 1 and len(stt.calls) == 1 + 2


def test_no_pipecat_interruption_fires_but_the_sessions(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The caller speaks over the reply twice, a listening sound, then a stop word: each turn's
    start broadcasts no interruption, and the session's one stop broadcasts Pipecat's one,
    from the session bridge (session_bridge.py), its two frames made once it was given. The
    stop word waits for the listening sound's turn to end, past the hold after Smart Turn's
    "complete" (`turns.complete_hold_ms`), so each is a turn and an overlap of its own."""
    stt, tts, watched = Hears(), PitchedSpeech([LONG]), watch(monkeypatch)
    app, emitted = echo_runtime(two_step(tmp_path), stt, tts)

    async def steps(browser: Browser, http: httpx.AsyncClient) -> None:
        await browser.connect(http)
        await over_the_reply(browser, stt, LISTENING)
        await until(lambda: bool(browser.of("unduck")), timeout=WAIT_S)
        await until(turns_ended(emitted, 2), timeout=WAIT_S)
        stt.now = STOP
        browser.signal.say(SPEECH_S)
        await until(lambda: len(browser.of("unduck")) == 2, timeout=WAIT_S)
        await until(lambda: browser.states()[-1] == "listening", timeout=WAIT_S)
        await until(turns_ended(emitted, 3), timeout=WAIT_S)
        await browser.hang_up()

    browser, left = run_call(app, steps)
    assert not left, left

    # Every `duck` ended with one `unduck`, each pair the session's for one overlap.
    ducks = [m["type"] for m in browser.messages if m.get("type") in ("duck", "unduck")]
    assert ducks == ["duck", "unduck", "duck", "unduck"]
    assert watched.named() == [
        *("duck", "HearOverlap", "unduck"),
        *("duck", "HearOverlap", "StopSpeaking", "unduck"),
    ]
    assert [e.turn_id for e in of(emitted, UserTurnEnded)] == [0, 1, 2]
    (stopped,) = watched.stops()
    assert watched.broadcasts == ["t2v-session-bridge"]
    assert len(watched.interruptions) == 2  # its frame downstream, and its sibling upstream
    assert all(stopped <= made for made in watched.interruptions)  # made once it was given
    assert [(e.kind, e.reason) for e in of(emitted, Interrupted)] == [
        ("false", "listening"),
        ("stop", "stop_word"),
    ]
