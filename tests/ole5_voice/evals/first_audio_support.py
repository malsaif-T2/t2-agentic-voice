"""What the tests of `poe first-audio` and `poe first-audio-listen` share: made-up recorded
requests, factories for `--agent` with the real one's signature, given the knowledge base (a
talker's with a made-up tool, none when given no base; an echo's; and a factory that gives no
agent) and for `--knowledge`, given the env file, a fake replay that answers each recording
from a script and keeps what it was asked (one also logs the talker's line), and a run's world
with the parts it is built from, so nothing is sent and no time passes but the run's own
pauses."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ole5_voice.evals.factories import load_factory
from ole5_voice.evals.first_audio_card import AudioScorecard
from ole5_voice.evals.first_audio_score import ChatSpend, ReplayedCall, ReplayedTurn
from ole5_voice.evals.first_audio_setup import FirstAudioParts
from ole5_voice.evals.models import Item
from ole5_voice.evals.runs import SCORECARD_FILE
from t2_agentic_voice import Language as Spoken
from t2_agentic_voice import VoiceAgent, VoiceSettings, get_logger
from t2_agentic_voice.events import ModelUsage
from t2_agentic_voice.ports import AudioChunk, AudioClip, KnowledgeBase

from tests.ole5_voice.evals.eot_support import Lines, golden_set, parts_of, paused
from tests.ole5_voice.evals.run_support import FakeClock, World, make_world
from tests.ole5_voice.evals.talker_fakes import FakeKnowledgeBase
from tests.ole5_voice.evals.timing_support import ARABIC, ENGLISH, WHISPER, FakePhraseCache
from tests.t2_agentic_voice.fakes import FakeSpeechToText, FakeTextToSpeech

CHAT = "openai/gpt-oss-120b"


@dataclass(frozen=True)
class MadeUpTool:
    """The smallest declared tool (the declaration's `DeclaredTool`)."""

    name: str = "search_made_up"
    description: str = "Looks a made-up thing up."
    progress: str | None = None


def _languages() -> list[Spoken]:
    """Saudi Arabic and English, as Ole5's talker speaks: no MSA of its own (its MSA callers are
    answered in MSA within the Saudi language)."""
    return [Spoken.saudi_arabic(greeting="مرحبا"), Spoken.english(greeting="Hello.")]


def agent(kb: KnowledgeBase | None = None) -> VoiceAgent:
    """A talker's agent with one tool searching `kb`, as the app's factory gives one; with no
    base, the same talker with no tool, as Ole5's `talker_agent(None)`."""
    tools = [MadeUpTool()] if kb is not None else []
    return VoiceAgent(name="made-up", languages=_languages(), instructions="Answer.", tools=tools)


def always_tools(kb: KnowledgeBase | None) -> VoiceAgent:
    """A factory that gives a tool even with no knowledge base."""
    return agent(kb or FakeKnowledgeBase())


def echo_agent(kb: KnowledgeBase | None) -> VoiceAgent:
    """An agent with no instructions: its calls run the echo."""
    return VoiceAgent(name="made-up", languages=_languages())


def english_agent(kb: KnowledgeBase | None) -> VoiceAgent:
    """A talker's agent that speaks English only."""
    return VoiceAgent(
        name="made-up", languages=[Spoken.english(greeting="Hello.")], instructions="Answer."
    )


def no_agent(kb: KnowledgeBase | None) -> str:
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
    repeats; an exception is raised), keeping what it was built with and asked, and how many
    calls it had been asked when its clause cache was cleared."""

    clock: FakeClock
    script: list[ReplayedCall | BaseException]
    built: dict[str, Any] = field(default_factory=dict)
    asked: list[dict[str, Any]] = field(default_factory=list)
    cleared: list[int] = field(default_factory=list)
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

    async def clear(self) -> None:
        self.cleared.append(len(self.asked))

    async def aclose(self) -> None:
        self.closed += 1


class Talking(FakeReplay):
    """The fake replay, each call logging the talker's line under the library's logger as the
    real replay's talker does (`talker_replied`, its search or none), and an error."""

    async def call(self, clip: AudioClip, **asked: Any) -> ReplayedCall:
        talker = get_logger("t2_agentic_voice.agent.turn")
        talker.info("talker_replied", tools=1)
        talker.error("made_up_failure")
        return await super().call(clip, **asked)


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
    kb: FakeKnowledgeBase = field(default_factory=FakeKnowledgeBase)
    env_files: list[Path | None] = field(default_factory=list)

    def load(self, spec: str) -> Callable[..., object]:
        """The factories `ole5_voice.fake:<name>` names: this module's agents, and a knowledge
        base's that keeps the env file it was given; any other spec as a run loads it."""
        module, _, name = spec.partition(":")

        def knowledge(env_file: Path | None) -> FakeKnowledgeBase:
            self.env_files.append(env_file)
            return self.kb

        made: dict[str, Callable[..., object]] = {
            "agent": agent,
            "always_tools": always_tools,
            "echo_agent": echo_agent,
            "english_agent": english_agent,
            "no_agent": no_agent,
            "kb": knowledge,
        }
        if module == "ole5_voice.fake" and name in made:
            return made[name]
        return load_factory(spec)

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
            "load_factory": self.load,
        }
        return FirstAudioParts(**(found | changed))

    @property
    def out(self) -> Path:
        return self.world.main / "var" / "runs" / "t1"

    def argv(self, *extra: str, split: str = "dev", factory: str = "agent") -> list[str]:
        knowledge = [] if "--no-tools" in extra else ["--knowledge", "ole5_voice.fake:kb"]
        return [
            *knowledge,
            "--split",
            split,
            "--agent",
            f"ole5_voice.fake:{factory}",
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
