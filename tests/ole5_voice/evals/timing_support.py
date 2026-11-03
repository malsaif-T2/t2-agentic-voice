"""What the tests of `poe eval-timing` share (test_timing.py, test_timing_refusals.py): a fake
`echo_timings`, a fake phrase cache, made-up echo calls, and a run's world with the parts it is
built from, so nothing is sent and no time passes."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ole5_voice.evals.runs import SCORECARD_FILE
from ole5_voice.evals.timing import TimingParts
from ole5_voice.evals.timing_score import TimingScorecard
from t2_agentic_voice import VoiceAgent, VoiceSettings
from t2_agentic_voice.evals import EchoTiming, TurnTiming
from t2_agentic_voice.events import ModelUsage
from t2_agentic_voice.ports import AudioChunk, AudioClip, TextToSpeech

from tests.ole5_voice.evals.eot_support import Lines, golden_set, parts_of, paused
from tests.ole5_voice.evals.run_support import FakeClock, World, make_world
from tests.t2_agentic_voice.fakes import FakeSpeechToText, FakeTextToSpeech

ARABIC = "canopylabs/orpheus-arabic-saudi"
ENGLISH = "canopylabs/orpheus-v1-english"
WHISPER = "whisper-large-v3"


def echo(turns: int = 1, *, failure: str | None = None, early: bool = False) -> EchoTiming:
    """A call of `turns` turns (the first ending 0.6 s before the mark when `early`), each with
    its echo, its last failing with `failure`; one Whisper request and one Orpheus request a
    turn."""
    found = []
    for n in range(turns):
        end = 1000.0 + 2000.0 * n if early else 1800.0 + 2000.0 * n
        found.append(
            TurnTiming(
                turn_id=n,
                speech_stop_ms=end - 300.0,
                end_ms=end,
                stt_sent_ms=end,
                stt_answered_ms=end + 270.0,
                echo_text_ms=end + 280.0,
                frame_audio_ms=end + 300.0,
                tts_sent_ms=end + 285.0,
                tts_first_audio_ms=end + 530.0,
                heard_sound_ms=end + 900.0,
                leading_silence_ms=450.0,
                failure=failure if n == turns - 1 else None,  # type: ignore[arg-type]
            )
        )
    usage = (
        ModelUsage(model=WHISPER, requests=turns, audio_sent_s=2.0, billed_s=10.0 * turns),
        ModelUsage(model=ARABIC, requests=turns, characters=55 * turns, cache_hits=turns + 1),
    )
    return EchoTiming(turns=tuple(found), usage=usage)


@dataclass
class FakeEchoTimings:
    """Stands in for `evals.echo_timings`: each call's timing from a script (the last repeats),
    each call's start time on the run's clock, and what it was given."""

    clock: FakeClock
    script: list[EchoTiming]
    started: list[float] = field(default_factory=list)
    asked: list[dict[str, Any]] = field(default_factory=list)

    async def __call__(
        self, clips: Iterable[tuple[AudioClip, str]], **asked: Any
    ) -> AsyncIterator[EchoTiming]:
        self.started.append(self.clock())
        self.asked.append({"clips": list(clips), **asked})
        found = self.script.pop(0) if len(self.script) > 1 else self.script[0]
        self.clock.now += 11.0  # a variant's call: greeting, lead, clip and tail
        yield found


class FakePhraseCache:
    """Stands in for `PhraseCache`: `declare` says it sent `requests`, `audio` plays silence."""

    def __init__(self, requests: int) -> None:
        self.requests = requests
        self.declared: list[VoiceAgent] = []

    async def declare(self, agent: VoiceAgent) -> int:
        self.declared.append(agent)
        return self.requests

    def audio(self, text: str, *, language: Any) -> AudioChunk:
        return AudioChunk(pcm16=b"", sample_rate=24_000)


@dataclass
class Setup:
    world: World
    clock: FakeClock
    echo: FakeEchoTimings
    cache: FakePhraseCache
    stt: FakeSpeechToText
    tts: FakeTextToSpeech
    lines: Lines

    def parts(self, variants: int = 3) -> TimingParts:
        found = [paused(self.world, f"p{n}") for n in range(variants)]
        found.append(paused(self.world, "e1", language="english"))
        plan = parts_of(self.world, golden_set(*found))
        plan = type(plan)(**{**plan.__dict__, "clock": self.clock, "sleep": self.clock.sleep})

        def cache(settings: VoiceSettings, tts: TextToSpeech) -> FakePhraseCache:
            return self.cache

        return TimingParts(
            plan=plan,
            speech_to_text=lambda settings: self.stt,
            text_to_speech=lambda settings: self.tts,
            phrases=cache,
            echo_timings=self.echo,
            append_line=self.lines,
        )

    def argv(self, *extra: str) -> list[str]:
        return [
            "--split",
            "dev",
            "--model",
            WHISPER,
            "--timeout-s",
            "6",
            "--out",
            str(self.out),
            "--audio",
            f"owner={self.world.audio}",
            "--price-per-hour",
            "0.111",
            "--tts-price",
            f"{ARABIC}=40",
            "--tts-price",
            f"{ENGLISH}=22",
            "--cap-usd",
            "1",
            "--note",
            "T1",
            *extra,
        ]

    @property
    def out(self) -> Path:
        return self.world.main / "var" / "runs" / "t1"

    def card(self) -> TimingScorecard:
        return TimingScorecard.model_validate_json((self.out / SCORECARD_FILE).read_bytes())


def make_setup(tmp_path: Path) -> Setup:
    clock = FakeClock()
    return Setup(
        world=make_world(tmp_path),
        clock=clock,
        echo=FakeEchoTimings(clock, [echo()]),
        cache=FakePhraseCache(6),
        stt=FakeSpeechToText(),
        tts=FakeTextToSpeech(),
        lines=Lines(),
    )
