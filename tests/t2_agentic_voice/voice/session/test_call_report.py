"""What a call reports (voice/session/call.py, usage.py, report.py; core/tracing_tts.py): usage
counted per model, every request that went counted (one the call's end cancelled included, and
the report of one that came after the end), Whisper billed at its 10 s minimum; the report's
file under `var_dir/reports/` holding no text of the call; one trace per turn, `session.id` set
to the call's ID, with its speech-to-text and text-to-speech spans and the resource attributes,
the report's numbers on the call's root span, and no secret or audio in any span; the browser's
view merged from its `client_stats`; and a step that fails logged, the call going on."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.events import CallEnded
from t2_agentic_voice.core.settings.storage import StorageSettings
from t2_agentic_voice.core.tracing_tts import SETTINGS_DIGEST, settings_digest
from t2_agentic_voice.domain.ports.speech_to_text import Transcript
from t2_agentic_voice.voice.protocol import Caption
from t2_agentic_voice.voice.session.commands import Command, Send, Speak
from t2_agentic_voice.voice.session.report import REPORTS
from t2_agentic_voice.voice.session.session_events import Transcribed

from tests.leaks import holding
from tests.t2_agentic_voice.core.tracing_support import (
    JOIN_KEY,
    MADE_UP_KEY,
    TURN_SECRET,
    exported_text,
)
from tests.t2_agentic_voice.session_fakes import FakeCommands, FakeSessionIO
from tests.t2_agentic_voice.voice.session.session_support import (
    HEARD,
    call,
    greeted,
    play,
    report,
    spans,
    speaks,
    traced,
    turn,
)

WHISPER = "whisper-large-v3"
ORPHEUS = "canopylabs/orpheus-v1-english"


def test_usage_is_counted_per_model(settings: VoiceSettings) -> None:
    """Two turns: Whisper's two requests, their audio sent and billed (10 s at least each) and
    the headroom its answer reported; Orpheus's requests, characters, the cache's hits (the
    greeting and two frames) and the headroom its response reported; and each model's requests
    per call minute."""
    io, session = call(settings)

    async def drive() -> None:
        await greeted(io)
        await turn(io, 0, HEARD, audio_s=4.0)
        await play(io, 1)
        await io.clock.advance(1.0)
        await io.turn_opened(1)
        await io.turn_closed(1)
        await io.transcribing(1, audio_s=12.0)
        heard = Transcript(
            text="more words", language="en", remaining_requests=17, remaining_tokens=900
        )
        await session.handle(
            Transcribed(turn_id=1, at=io.clock.now(), audio_s=12.0, sent_at=None, transcript=heard)
        )
        for speak in speaks(io, 2):
            if speak.audio is None:
                await io.synthesizing(2, speak.clause)
            await io.clause_queued(2, speak.clause)
            await io.clause_played(2, speak.clause, remaining=(8, 4000))
        await io.ending()
        await io.close()

    asyncio.run(drive())
    sent = [s for s in speaks(io) if s.audio is None]
    whisper, orpheus = report(io).usage
    assert (whisper.model, whisper.requests, whisper.audio_sent_s, whisper.billed_s) == (
        WHISPER,
        2,
        16.0,
        22.0,
    )
    assert (whisper.remaining_requests, whisper.remaining_tokens) == (17, 900)
    assert (orpheus.model, orpheus.requests, orpheus.cache_hits) == (ORPHEUS, len(sent), 3)
    assert orpheus.characters == sum(len(s.text) for s in sent)
    assert (orpheus.remaining_requests, orpheus.remaining_tokens) == (8, 4000)
    rates = report(io).requests_per_minute()
    assert rates[WHISPER] == pytest.approx(2 / (report(io).duration_s / 60))


def test_a_whisper_request_the_end_cancelled_is_billed_at_its_minimum(
    settings: VoiceSettings,
) -> None:
    """`TurnClosed`, its `Transcribing` with 4.0 s, then an `Ending`: one request, 4.0 s sent
    and 10.0 s billed, the turn unfinished."""
    io, _ = call(settings)

    async def drive() -> None:
        await io.connected()
        await io.turn_opened(0)
        await io.turn_closed(0)
        await io.transcribing(0, audio_s=4.0)
        await io.ending()
        await io.close()

    asyncio.run(drive())
    whisper = report(io).usage[0]
    assert (whisper.requests, whisper.audio_sent_s, whisper.billed_s) == (1, 4.0, 10.0)
    assert report(io).turns[0].unfinished


def test_every_request_that_went_is_counted_one_the_end_cancelled_included(
    settings: VoiceSettings,
) -> None:
    """Turn 0's echo sends its first clause of heard words, and the caller leaves before its
    first audio; turn 1 closes with its transcript to come. The reports of turn 1's request and
    of the echo's second clause come after the end. Every request counts: Whisper's two, 1 s and
    4 s sent and 10 s each billed, and Orpheus's two with their characters."""
    io, _ = call(settings, max_chars=12)

    async def drive() -> None:
        await greeted(io)
        await turn(io, 0, HEARD)
        await io.clause_queued(1, 0)
        await io.synthesizing(1, 1)
        await io.turn_opened(1)
        await io.turn_closed(1)
        await io.ending()
        await io.transcribing(1, audio_s=4.0)  # their reports, handed after the end
        await io.synthesizing(1, 2)
        await io.close()

    asyncio.run(drive())
    whisper, orpheus = report(io).usage
    assert (whisper.requests, whisper.audio_sent_s, whisper.billed_s) == (2, 5.0, 20.0)
    words = speaks(io, 1)[1:]
    assert len(words) == 2 and (orpheus.requests, orpheus.characters) == (
        2,
        len("".join(w.text for w in words)),
    )
    assert [t.unfinished for t in report(io).turns] == [False, True]


def test_the_report_file_holds_the_calls_numbers_and_no_text_of_it(
    settings: VoiceSettings,
) -> None:
    """The file under `var_dir/reports/` holds the call's numbers (its usage, requests per call
    minute, each turn's outcome and times, the browser's view) and none of what was heard or
    said, while the `CallReport` the observers get holds both."""
    io, _ = call(settings)
    language = io.setup.language

    async def drive() -> None:
        await greeted(io)
        await turn(io, 0, HEARD)
        await play(io, 1)
        await io.client(
            {"v": 1, "type": "client_stats", "candidate_type": "host", "connect_ms": 80}
        )
        await io.ending()
        await io.close()

    asyncio.run(drive())
    path = settings.storage.var_dir / REPORTS / "call-1.json"
    text = path.read_text(encoding="utf-8")
    for words in (HEARD, language.greeting, language.echo_frame, *HEARD.split()):
        assert words not in text
    data = json.loads(text)
    assert data["call_id"] == "call-1" and data["ended_by"] == "caller_left"
    assert set(data["requests_per_minute"]) == {WHISPER, ORPHEUS}
    assert data["turns"][0]["times"]["ttfa_ms"] is not None
    assert "heard" not in data["turns"][0] and "said" not in data["turns"][0]
    assert data["client"]["candidate_type"] == "host"
    assert report(io).turns[0].heard == HEARD and HEARD in report(io).turns[0].said
    assert not list((settings.storage.var_dir / REPORTS).glob("*.tmp"))


def test_a_report_that_cannot_be_written_is_logged_and_still_observed(
    settings: VoiceSettings, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    blocked = tmp_path / "a-file"
    blocked.write_text("", encoding="utf-8")
    io, _ = call(settings.model_copy(update={"storage": StorageSettings(var_dir=blocked)}))

    async def drive() -> None:
        await greeted(io)
        await io.ending()
        await io.close()

    asyncio.run(drive())
    assert [e for e in io.emitted if isinstance(e, CallEnded)]
    assert "report_not_written" in [r.getMessage() for r in caplog.records]


def _secret_settings(tmp_path: Path) -> VoiceSettings:
    return VoiceSettings.model_validate(
        {
            "env": "test",
            "storage": {"var_dir": tmp_path / "var"},
            "groq": {"api_key": MADE_UP_KEY},
            "join": {"keys": {"k1": JOIN_KEY}},
            "server": {"turn_secret": TURN_SECRET},
            "privacy": {"consent_version": "v1"},
        }
    )


def test_one_trace_per_turn_with_its_spans_and_no_secret_in_any(tmp_path: Path) -> None:
    """Each turn is a trace of its own, its root span's `session.id` the call's ID, holding the
    speech-to-text span and its echo's text-to-speech span (characters, chunks, requests, time
    to first audio, cache hits); the greeting's goes under the call's own root span, which
    carries the report's numbers; every root span carries the resource attributes, the settings'
    digest among them; no span holds a secret, and none holds audio."""
    settings = _secret_settings(tmp_path)
    io, session, exporter = traced(settings)

    async def drive() -> None:
        await greeted(io)
        await turn(io, 0, HEARD)
        await play(io, 1)
        await turn(io, 1, None)
        await io.ending()
        await io.close()

    asyncio.run(drive())
    found = spans(session, exporter)
    roots = [s for s in found if s.parent is None]
    assert sorted(s.name for s in roots) == ["call", "turn", "turn"]
    assert {s.attributes["session.id"] for s in roots} == {"call-1"}  # type: ignore[index]
    assert {s.attributes[SETTINGS_DIGEST] for s in roots} == {settings_digest(settings)}  # type: ignore[index]
    assert len({s.context.trace_id for s in roots}) == 3
    first = next(s for s in roots if s.name == "turn" and s.attributes["turn.id"] == 0)  # type: ignore[index]
    children = {s.name: s for s in found if s.parent and s.parent.span_id == first.context.span_id}
    assert set(children) == {"speech_to_text", "text_to_speech"}
    tts = children["text_to_speech"].attributes or {}
    words = [s for s in speaks(io, 1) if s.audio is None]
    assert (tts["tts.requests"], tts["tts.cache_hits"]) == (len(words), 1)
    assert tts["tts.characters"] == sum(len(s.text) for s in words)
    assert tts["tts.chunks"] == 2 * len(speaks(io, 1)) and "tts.first_audio_ms" in tts
    call_span = next(s for s in roots if s.name == "call")
    greeting = [s for s in found if s.parent and s.parent.span_id == call_span.context.span_id]
    assert [s.name for s in greeting] == ["text_to_speech"]
    numbers = call_span.attributes or {}
    assert numbers["call.turns"] == 2 and numbers[f"usage.{WHISPER}.requests"] == 2
    shown = exported_text(found)
    for secret in (MADE_UP_KEY, JOIN_KEY, TURN_SECRET):
        assert holding(secret, {"spans": shown}) == []
    assert "bytes" not in shown and HEARD not in repr(tts)


RELAY = {"v": 1, "type": "client_stats", "candidate_type": "relay", "relay_protocol": "udp"}
PLAYED = {"v": 1, "type": "client_stats", "first_audio_ms": 300}
HOST = {"v": 1, "type": "client_stats", "candidate_type": "host"}


@pytest.mark.parametrize(
    ("stats", "view"),
    [
        (
            [RELAY, PLAYED],
            {"candidate_type": "relay", "relay_protocol": "udp", "first_audio_ms": 300},
        ),
        ([RELAY, HOST], {"candidate_type": "host"}),
    ],
    ids=["merged", "contradicted"],
)
def test_the_browsers_view_is_merged_from_its_client_stats(
    settings: VoiceSettings, stats: list[dict[str, object]], view: dict[str, object]
) -> None:
    """Each `client_stats` adds what the browser learned; one that contradicts the last (a
    relay become a host) is taken alone. The client's other messages change nothing of it."""
    io, _ = call(settings)

    async def drive() -> None:
        await io.connected()
        for message in stats:
            await io.client(message)
        await io.client({"v": 1, "type": "hello", "client": "t2v-client.js/1.0.0"})
        await io.client(
            {"v": 1, "type": "playback", "reply_id": 0, "clause": 0, "event": "started"}
        )
        await io.ending()
        await io.close()

    asyncio.run(drive())
    client = report(io).client
    assert client is not None and client.model_dump(exclude_none=True) == view


class _FailsOnce(FakeCommands):
    """Where the session's commands go, failing the first agent caption."""

    def __init__(self, kept: FakeCommands) -> None:
        super().__init__()
        self.commands = kept.commands
        self.failed = False

    async def run(self, command: Command) -> None:
        message = command.message if isinstance(command, Send) else None
        if isinstance(message, Caption) and not self.failed:
            self.failed = True
            raise RuntimeError("the fake's own failure")
        await super().run(command)


def test_a_step_that_fails_is_logged_by_its_kind_and_the_call_goes_on(
    settings: VoiceSettings, caplog: pytest.LogCaptureFixture, step_failures: None
) -> None:
    from t2_agentic_voice.voice.session.call import CallSession

    io = FakeSessionIO(settings)
    session = CallSession(io.setup, _FailsOnce(io.commands))
    io.attach(session)

    async def drive() -> None:
        await greeted(io)  # the greeting's caption fails
        await turn(io, 0, HEARD)
        await play(io, 1)
        await io.ending()
        await io.close()

    asyncio.run(drive())
    failed = [r for r in caplog.records if r.getMessage() == "session_step_failed"]
    assert [getattr(r, "fields", {}).get("failure") for r in failed] == ["RuntimeError"]
    assert "the fake's own failure" not in caplog.text
    assert [s.reply_id for s in speaks(io) if isinstance(s, Speak)][-1] == 1
    assert report(io).turns[0].said


def test_a_timer_that_fails_gives_up_and_the_call_goes_on(
    settings: VoiceSettings,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    step_failures: None,
) -> None:
    io, session = call(settings)

    async def broken(limit: str) -> None:
        raise RuntimeError("the test's own failure")

    monkeypatch.setattr(session, "_limit", broken)

    async def drive() -> None:
        await greeted(io)
        await io.clock.advance(settings.limits.max_call_s)
        await turn(io, 0, HEARD)
        await io.ending()
        await io.close()

    asyncio.run(drive())
    assert speaks(io, 1) and report(io).ended_by == "caller_left"
    failed = [r for r in caplog.records if r.getMessage() == "session_step_failed"]
    assert [getattr(r, "fields", {}).get("step") for r in failed] == ["idle", "max_call"]
