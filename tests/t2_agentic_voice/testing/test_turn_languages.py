"""Each turn's language in a file-fed call (testing/turn_languages.py; D-086, run H's
H1), against a fake `VoiceCalls` and a fake `feed_file` that play a call's events and ask the
classifier the helper gave them, on a clock that moves only when the test moves it, so no model
loads and no time passes: what each turn records (its end, the language its request named and
how, when that was decided and on how much speech, and the classification's ask, verdict and
time, each counted from the clip's first frame); `chosen`, the rule read back for any call
language, which gives the live call's own choices for the language it was held in; the wrapper
that keeps each classification; and the refusals before any call."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

import pytest
from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.errors import ProviderError
from t2_agentic_voice.core.events import LanguageBy
from t2_agentic_voice.core.settings.stt import SttSettings
from t2_agentic_voice.domain.declaration import Language
from t2_agentic_voice.domain.ports.language_classifier import LanguageScores
from t2_agentic_voice.domain.ports.speech_to_text import AudioClip
from t2_agentic_voice.domain.turn_language import LanguageChoice
from t2_agentic_voice.testing import turn_languages as module
from t2_agentic_voice.testing.turn_languages import LanguageTurn, chosen, turn_languages
from t2_agentic_voice.voice import file_transport
from t2_agentic_voice.voice.file_transport import FedCall
from t2_agentic_voice.voice.session.session_events import (
    SessionEvent,
    Transcribing,
    TurnClosed,
    TurnOpened,
)

from tests.t2_agentic_voice.fakes import FakeClock
from tests.t2_agentic_voice.testing.feed_support import FakeVoiceCalls

SECOND = AudioClip(pcm16=b"\x00\x00" * 16_000)
LANGUAGES = (Language.saudi_arabic(greeting="Hala."), Language.english(greeting="Welcome."))
ENGLISH = {"ar": 0.1, "en": 0.9}
UNSURE = {"ar": 0.4, "en": 0.6}


def _settings(live: str = "classified") -> VoiceSettings:
    return VoiceSettings(env="test", stt=SttSettings(live_language=live))  # type: ignore[arg-type]


class ClockedClassifier:
    """A classifier whose every classification takes `took_s` on the test's clock and answers
    from a script (shares, None for busy, a `ProviderError`, or an answer that does not parse)."""

    name = "clocked"

    def __init__(self, clock: FakeClock, script: Sequence[object], took_s: float) -> None:
        self.clock, self.script, self.took_s = clock, list(script), took_s
        self.loaded: list[tuple[str, ...]] = []
        self.closed = 0

    async def load(self, among: Sequence[str]) -> None:
        self.loaded.append(tuple(among))

    async def classify(self, clip: AudioClip, *, among: Sequence[str]) -> LanguageScores | None:
        await self.clock.sleep(self.took_s)
        entry = self.script.pop(0)
        if isinstance(entry, ProviderError):
            raise entry
        if isinstance(entry, dict):
            return LanguageScores.parsed(entry, among=among, mass=0.8)
        return entry  # type: ignore[return-value]  # None (busy), or an answer that does not parse

    async def aclose(self) -> None:
        self.closed += 1


# One call's script: given what `VoiceCalls` was built with, the call's events.
Script = Callable[[dict[str, Any]], Awaitable[FedCall]]


@dataclass
class ScriptedFeed:
    """Stands in for `VoiceCalls` and `feed_file`: each call runs the next script."""

    scripts: list[Script]
    asked: list[dict[str, Any]] = field(default_factory=list)
    built: list[FakeVoiceCalls] = field(default_factory=list)

    def voice_calls(self, **built: Any) -> FakeVoiceCalls:
        made = FakeVoiceCalls(built)
        self.built.append(made)
        return made

    async def __call__(self, calls: FakeVoiceCalls, clip: AudioClip, **asked: Any) -> FedCall:
        assert calls.started == 1 and not calls.closed
        self.asked.append({"clip": clip, **asked})
        return await self.scripts.pop(0)(calls.built)


@pytest.fixture
def feed(monkeypatch: pytest.MonkeyPatch) -> ScriptedFeed:
    faked = ScriptedFeed([])
    monkeypatch.setattr(module, "VoiceCalls", faked.voice_calls)
    monkeypatch.setattr(file_transport, "feed_file", faked)
    return faked


async def _ask(built: dict[str, Any], clock: FakeClock, wait_s: float) -> asyncio.Task[object]:
    """The call's classifier asked now, as the bridge asks it, on a task of its own; the clock
    then moved `wait_s` on."""
    task = asyncio.create_task(built["classifier"].classify(SECOND, among=("ar", "en")))
    await asyncio.sleep(0)
    await clock.advance(wait_s)
    return task


def _request(turn_id: int, at: float, by: LanguageBy, language: str, **more: Any) -> Transcribing:
    return Transcribing(
        turn_id=turn_id, at=at, audio_s=2.0, language=language, language_by=by, **more
    )


def _run(found: AsyncIterator[tuple[LanguageTurn, ...]]) -> list[tuple[LanguageTurn, ...]]:
    async def every() -> list[tuple[LanguageTurn, ...]]:
        return [turns async for turns in found]

    return asyncio.run(every())


def test_each_turn_records_its_language_its_decision_and_its_classification(
    feed: ScriptedFeed,
) -> None:
    """Turn 0's verdict came before its hold began (classified); turn 1's came after it (late);
    turn 2 was too short to ask. Every time counts from the clip's first frame, at 10.0."""
    clock = FakeClock(start=10.0)
    classifier = ClockedClassifier(clock, [ENGLISH, ENGLISH], took_s=0.3)

    async def call(built: dict[str, Any]) -> FedCall:
        events: list[SessionEvent] = [TurnOpened(turn_id=0, at=11.0, speech_at=10.7)]
        await clock.advance(1.5)  # 11.5: two seconds of speech held
        first = await _ask(built, clock, 0.5)  # its verdict comes at 11.8; the hold at 12.0
        await first
        events += [
            _request(0, 12.6, "classified", "en", share=0.9, decided_at=12.0, speech_s=2.4),
            TurnClosed(turn_id=0, at=12.6, speech_ended_at=11.9),
            TurnOpened(turn_id=1, at=13.0, speech_at=12.8),
        ]
        await clock.advance(1.0)  # 13.0
        await clock.advance(0.6)  # 13.6: asked; the hold begins at 13.8, its verdict at 13.9
        second = await _ask(built, clock, 0.3)
        await second
        events += [
            _request(1, 14.4, "late", "en", decided_at=13.8, speech_s=2.2),
            TurnClosed(turn_id=1, at=14.4, speech_ended_at=13.7),
            TurnOpened(turn_id=2, at=15.0, speech_at=14.9),
            _request(2, 15.8, "short", "en", decided_at=15.8, speech_s=0.6),
            TurnClosed(turn_id=2, at=15.8, speech_ended_at=15.5),
        ]
        return FedCall(started_at=10.0, events=tuple(events), commands=())

    feed.scripts = [call]
    found = turn_languages(
        [SECOND],
        languages=LANGUAGES,
        settings=_settings(),
        classifier=classifier,
        lead_s=1.0,
        tail_s=4.5,
        _clock=clock,
    )
    ((first, second, short),) = _run(found)
    assert (first.speech_stop_ms, first.end_ms) == pytest.approx((1900.0, 2600.0))
    assert (first.named, first.by) == ("en", "classified")
    assert first.decided_ms == pytest.approx(2000.0)
    assert (first.asked_ms, first.verdict_ms) == pytest.approx((1500.0, 1800.0))
    assert isinstance(first.verdict, LanguageScores) and first.verdict.best == ("en", 0.9)
    assert (second.by, second.speech_s) == ("late", 2.2)
    assert second.decided_ms == pytest.approx(3800.0)
    assert (second.asked_ms, second.verdict_ms) == pytest.approx((3600.0, 3900.0))
    assert (short.by, short.asked_ms, short.verdict) == ("short", None, None)
    # The call was held in Arabic: read back for Arabic, the rule gives what the call named.
    live = chosen((first, second, short), current="ar", from_s=2.0, min_share=0.7)
    assert [(c.language, c.by) for c in live] == [(t.named, t.by) for t in (first, second, short)]
    assert classifier.loaded == [("ar", "en")] and classifier.closed == 0
    (calls,) = feed.built
    assert (calls.started, calls.closed) == (1, 1)
    assert calls.built["classifier"].name == "clocked" and calls.built["clock"] is clock
    assert feed.asked[0]["language"] == LANGUAGES[0]
    assert feed.asked[0]["call_id"] == "turn-languages-0"


def _turn(by: LanguageBy | None, **fields: Any) -> LanguageTurn:
    return LanguageTurn(speech_stop_ms=1000.0, end_ms=1500.0, by=by, **fields)


def _scores(shares: dict[str, float]) -> LanguageScores:
    return LanguageScores.parsed(shares, among=("ar", "en"), mass=0.9)


def test_chosen_reads_each_turn_with_the_rule_as_a_call_held_in_another_language_decides() -> None:
    """A verdict counts as in hand only when it came by the decision (at it too); only a
    classified turn moves the current language, which later turns keep; a short, late, unsure,
    busy or failed turn, an overlap's and a session's keep it."""
    in_time = {"decided_ms": 2000.0, "speech_s": 2.4, "asked_ms": 1500.0}
    turns = (
        _turn("late", **in_time, verdict_ms=2000.0, verdict=_scores(ENGLISH)),  # at the decision
        _turn("short", decided_ms=3000.0, speech_s=1.2),
        _turn("classified", **in_time, verdict_ms=2001.0, verdict=_scores(ENGLISH)),  # late here
        _turn("unsure", **in_time, verdict_ms=1800.0, verdict=_scores(UNSURE)),
        _turn("busy", **in_time, verdict_ms=1600.0, verdict="busy"),
        _turn("failed", **in_time, verdict_ms=1600.0, verdict="failed"),
        _turn("overlap"),
        _turn(None),  # no request went: nothing in hand, no speech
    )
    english = chosen(turns, current="en", from_s=2.0, min_share=0.7)
    arabic = chosen(turns, current="ar", from_s=2.0, min_share=0.7)
    assert [c.by for c in english] == [c.by for c in arabic]
    assert [c.by for c in arabic] == [
        "classified",
        "short",
        "late",
        "unsure",
        "busy",
        "failed",
        "overlap",
        "short",
    ]
    assert {c.language for c in english} == {"en"}
    assert [c.language for c in arabic] == ["en"] * 8  # the first moved it, the rest keep it
    session = chosen([_turn("session"), _turn("session")], current="ar", from_s=2.0, min_share=0.7)
    assert session == (LanguageChoice(language="ar", by="session"),) * 2
    stricter = chosen(turns[:1], current="ar", from_s=2.5, min_share=0.7)
    assert stricter == (LanguageChoice(language="ar", by="short"),)
    assert chosen((), current="ar", from_s=2.0, min_share=0.7) == ()


def test_the_wrapper_keeps_busy_failed_malformed_and_cancelled_classifications(
    feed: ScriptedFeed,
) -> None:
    """What the classifier gave is kept as the bridge reads it, and handed on unchanged: None is
    busy, a `ProviderError` (raised on) and an answer that does not parse are failed, and a
    classification the call's end cancelled has no verdict and no time."""
    clock = FakeClock(start=0.0)
    failure = ProviderError("server_error", False)
    classifier = ClockedClassifier(clock, [None, failure, "not scores"], took_s=0.1)
    handed: list[object] = []

    async def call(built: dict[str, Any]) -> FedCall:
        events: list[SessionEvent] = []
        for turn_id in range(4):
            events.append(TurnOpened(turn_id=turn_id, at=clock.now(), speech_at=clock.now()))
            await clock.advance(0.5)
            task = await _ask(built, clock, 0.0 if turn_id == 3 else 0.2)
            if turn_id == 3:
                task.cancel()
            handed.append((await asyncio.gather(task, return_exceptions=True))[0])
            events.append(TurnClosed(turn_id=turn_id, at=clock.now(), speech_ended_at=clock.now()))
        return FedCall(started_at=0.0, events=tuple(events), commands=())

    feed.scripts = [call]
    found = turn_languages(
        [SECOND],
        languages=LANGUAGES,
        settings=_settings(),
        classifier=classifier,
        lead_s=1.0,
        tail_s=4.5,
        _clock=clock,
    )
    ((busy, failed, malformed, cancelled),) = _run(found)
    assert [busy.verdict, failed.verdict, malformed.verdict] == ["busy", "failed", "failed"]
    assert busy.verdict_ms == pytest.approx(600.0) and busy.asked_ms == pytest.approx(500.0)
    assert (cancelled.asked_ms is not None, cancelled.verdict_ms, cancelled.verdict) == (
        True,
        None,
        None,
    )
    assert handed[:3] == [None, failure, "not scores"]
    assert isinstance(handed[3], asyncio.CancelledError)
    assert (busy.named, busy.by) == (None, None)  # no request went in this made-up call


def test_a_call_with_no_classifier_names_the_sessions_language(feed: ScriptedFeed) -> None:
    async def call(built: dict[str, Any]) -> FedCall:
        assert built["classifier"] is None
        events = (
            TurnOpened(turn_id=0, at=1.2, speech_at=1.1),
            _request(0, 2.0, "session", "ar"),
            TurnClosed(turn_id=0, at=2.0, speech_ended_at=1.8),
        )
        return FedCall(started_at=1.0, events=events, commands=())

    feed.scripts = [call, call]
    found = turn_languages(
        [SECOND, SECOND],
        languages=LANGUAGES,
        settings=_settings("session"),
        classifier=None,
        lead_s=1.0,
        tail_s=4.5,
    )
    ((one,), (two,)) = _run(found)
    assert one == two and (one.named, one.by, one.decided_ms, one.asked_ms) == (
        "ar",
        "session",
        None,
        None,
    )
    assert [asked["call_id"] for asked in feed.asked] == ["turn-languages-0", "turn-languages-1"]


@pytest.mark.parametrize(
    ("clips", "languages", "live", "given", "says"),
    [
        ([AudioClip(pcm16=b"\x00\x00", sample_rate=8_000)], LANGUAGES, "session", False, "16000"),
        ([SECOND], LANGUAGES[:1], "session", False, "two languages"),
        ([SECOND], LANGUAGES, "classified", False, "classified"),
        ([SECOND], LANGUAGES, "session", True, "classified"),
        ([SECOND], LANGUAGES, "auto", False, "session or classified"),
    ],
)
def test_what_cannot_be_measured_is_refused_before_any_call(
    feed: ScriptedFeed,
    clips: list[AudioClip],
    languages: Sequence[Language],
    live: str,
    given: bool,
    says: str,
) -> None:
    classifier = ClockedClassifier(FakeClock(), [], took_s=0.0) if given else None
    found = turn_languages(
        clips,
        languages=languages,
        settings=_settings(live),
        classifier=classifier,
        lead_s=1.0,
        tail_s=4.5,
    )
    with pytest.raises(ValueError, match=says):
        _run(found)
    assert feed.built == [] and feed.asked == []
    assert classifier is None or classifier.loaded == []


def test_a_turn_is_plain_data_that_reads_back_from_json() -> None:
    turn = _turn(
        "classified",
        named="en",
        decided_ms=2000.0,
        speech_s=2.4,
        asked_ms=1500.0,
        verdict_ms=1800.0,
        verdict=_scores(ENGLISH),
    )
    assert LanguageTurn.model_validate_json(turn.model_dump_json()) == turn
    busy = _turn("busy", verdict="busy")
    assert LanguageTurn.model_validate_json(busy.model_dump_json()) == busy
    with pytest.raises(ValueError, match="frozen"):
        turn.end_ms = 2.0  # type: ignore[misc]
