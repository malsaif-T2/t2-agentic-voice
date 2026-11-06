"""What the tests of `poe first-audio` and `poe first-audio-listen` share: made-up recorded
requests, agents for `--agent` (a talker's with a made-up tool, an echo's, and a factory that
gives no agent), a fake replay that answers each recording from a script and keeps what it was
asked, and a run's world with the parts it is built from, so nothing is sent and no time
passes but the run's own pauses."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ole5_voice.evals.first_audio_card import AudioScorecard
from ole5_voice.evals.first_audio_score import ChatSpend, ReplayedCall, ReplayedTurn
from ole5_voice.evals.first_audio_setup import FirstAudioParts
from ole5_voice.evals.models import Item
from ole5_voice.evals.runs import SCORECARD_FILE
from t2_agentic_voice import Language as Spoken
from t2_agentic_voice import VoiceAgent, VoiceSettings
from t2_agentic_voice.events import ModelUsage
from t2_agentic_voice.ports import AudioChunk, AudioClip

from tests.ole5_voice.evals.eot_support import Lines, golden_set, parts_of, paused
from tests.ole5_voice.evals.run_support import FakeClock, World, make_world
from tests.ole5_voice.evals.timing_support import ARABIC, ENGLISH, WHISPER, FakePhraseCache
from tests.t2_agentic_voice.fakes import FakeSpeechToText, FakeTextToSpeech

CHAT = "openai/gpt-oss-120b"
SUPPORT = "tests.ole5_voice.evals.first_audio_support"


@dataclass(frozen=True)
class MadeUpTool:
    """The smallest declared tool (the declaration's `DeclaredTool`)."""

    name: str = "search_made_up"
    description: str = "Looks a made-up thing up."
    progress: str | None = None


def _languages() -> list[Spoken]:
    return [
        Spoken.saudi_arabic(greeting="مرحبا"),
        Spoken.arabic(greeting="مرحبا"),
        Spoken.english(greeting="Hello."),
    ]


def agent() -> VoiceAgent:
    """A talker's agent with one tool, as the app's factory gives one."""
    return VoiceAgent(
        name="made-up", languages=_languages(), instructions="Answer.", tools=[MadeUpTool()]
    )


def echo_agent() -> VoiceAgent:
    """An agent with no instructions: its calls run the echo."""
    return VoiceAgent(name="made-up", languages=_languages())


def english_agent() -> VoiceAgent:
    """A talker's agent that speaks English only."""
    return VoiceAgent(
        name="made-up", languages=[Spoken.english(greeting="Hello.")], instructions="Answer."
    )


def no_agent() -> str:
    """A factory that gives something else."""
    return "not an agent"


def call(*turns: ReplayedTurn, opening: bool = True, remaining: int | None = None) -> ReplayedCall:
    """A replayed call of `turns` (one quick reply with a search by default), each reply's
    opening a short tone, a Whisper request and an Orpheus request a turn, and the chat
    model's two requests a turn."""
    found = turns or (ReplayedTurn(ttfa_ms=2500.0, searched=True, progress_ms=1800.0),)
    tone = AudioChunk(pcm16=b"\x10\x00" * 2400, sample_rate=24_000)
    return ReplayedCall(
        turns=found,
        openings=tuple(tone if opening else None for _ in found),
        usage=(
            ModelUsage(
                model=WHISPER,
                requests=len(found),
                billed_s=10.0 * len(found),
                remaining_requests=remaining,
            ),
            ModelUsage(model=ARABIC, requests=len(found), characters=60 * len(found)),
        ),
        chat=ChatSpend(
            requests=2 * len(found), input_tokens=900, cached_tokens=300, output_tokens=40
        ),
    )


@dataclass
class FakeReplay:
    """Stands in for the replay: each recording answered by the next of `script` (the last
    repeats; an exception is raised), keeping what it was built with and asked."""

    clock: FakeClock
    script: list[ReplayedCall | BaseException]
    built: dict[str, Any] = field(default_factory=dict)
    asked: list[dict[str, Any]] = field(default_factory=list)
    started: int = 0
    closed: int = 0

    def __call__(self, **built: Any) -> FakeReplay:
        self.built = built
        return self

    async def start(self) -> None:
        self.started += 1

    async def call(self, clip: AudioClip, **asked: Any) -> ReplayedCall:
        self.asked.append({"clip": clip, "at": self.clock.now, **asked})
        self.clock.now += 12.0  # a call: greeting, lead, the recording, the reply and the tail
        found = self.script.pop(0) if len(self.script) > 1 else self.script[0]
        if isinstance(found, BaseException):
            raise found
        return found

    async def aclose(self) -> None:
        self.closed += 1


def recorded(world: World) -> list[Item]:
    """Two dev recorded requests (one marked, one not), an English one, and an item the knowledge
    set does not record."""
    return [
        paused(world, "n20_made_up", end_ms=1500),
        paused(world, "n02_made_up", kind="request"),
        paused(world, "n21_made_up", language="english", kind="request"),
        paused(world, "s01_made_up", kind="request"),
    ]


@dataclass
class TRun:
    """A run's world: its items, parts, replay, adapters, phrase cache, clock and history."""

    world: World
    clock: FakeClock
    replay: FakeReplay
    items: list[Item]
    held_out: tuple[str, ...] = ()
    cache: FakePhraseCache = field(default_factory=lambda: FakePhraseCache(4))
    stt: FakeSpeechToText = field(default_factory=FakeSpeechToText)
    tts: FakeTextToSpeech = field(default_factory=FakeTextToSpeech)
    lines: Lines = field(default_factory=Lines)
    built: list[VoiceSettings] = field(default_factory=list)

    def parts(self, **changed: Any) -> FirstAudioParts:
        plan = parts_of(self.world, golden_set(*self.items, held_out=self.held_out))
        plan = type(plan)(**{**plan.__dict__, "clock": self.clock, "sleep": self.clock.sleep})

        def chat(settings: VoiceSettings) -> Any:
            self.built.append(settings)
            return self.stt  # any adapter with aclose: the fake replay sends nothing to it

        found: dict[str, Any] = {
            "plan": plan,
            "speech_to_text": lambda settings: self.stt,
            "text_to_speech": lambda settings: self.tts,
            "chat_model": chat,
            "phrases": lambda settings, tts, agent: self.cache,
            "replay": self.replay,
            "append_line": self.lines,
        }
        return FirstAudioParts(**(found | changed))

    @property
    def out(self) -> Path:
        return self.world.main / "var" / "runs" / "t1"

    def argv(self, *extra: str, split: str = "dev", factory: str = "agent") -> list[str]:
        return [
            "--split",
            split,
            "--agent",
            f"{SUPPORT}:{factory}",
            "--trim-silence",
            "on",
            "--model",
            WHISPER,
            "--timeout-s",
            "6",
            "--llm-model",
            CHAT,
            "--llm-reasoning-effort",
            "low",
            "--llm-max-output-tokens",
            "512",
            "--llm-timeout-s",
            "8",
            "--llm-input-tokens",
            "4000",
            "--audio",
            f"owner={self.world.audio}",
            "--price-per-hour",
            "0.111",
            "--tts-price",
            f"{ARABIC}=40",
            "--tts-price",
            f"{ENGLISH}=22",
            "--llm-price-input",
            "0.15",
            "--llm-price-output",
            "0.6",
            "--cap-usd",
            "5",
            "--out",
            str(self.out),
            "--note",
            "T1",
            *extra,
        ]

    def card(self) -> AudioScorecard:
        return AudioScorecard.model_validate_json((self.out / SCORECARD_FILE).read_bytes())


def t_run(tmp_path: Path, *script: ReplayedCall | BaseException, **kept: Any) -> TRun:
    clock = FakeClock()
    world = make_world(tmp_path)
    items = kept.pop("items", None)
    return TRun(
        world,
        clock,
        FakeReplay(clock, list(script) or [call()]),
        recorded(world) if items is None else items(world),
        **kept,
    )
