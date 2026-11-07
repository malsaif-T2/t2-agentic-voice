"""What the tests of `poe uncertain` share (test_uncertain*.py): made-up stored overlap runs and
their recordings, a fake replay that judges each again by a made-up rule on the transcripts the
stored run heard, a fake chat model that answers from a script and keeps every request, and a
run's world (a checkout with a run worktree and its golden set, a clock that moves only when the
run pauses, the history lines)."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from ole5_voice.evals.models import Item, Kind, Split
from ole5_voice.evals.overlap_card import OverlapRun, OverlapScorecard, breakdowns
from ole5_voice.evals.overlap_score import (
    Action,
    Heard,
    OverlapResult,
    Part,
    Verdict,
    judge,
    metrics,
    targets,
)
from ole5_voice.evals.run_parts import Parts
from ole5_voice.evals.runs import SCORECARD_FILE
from ole5_voice.evals.uncertain import UncertainParts
from t2_agentic_voice import ProviderError, VoiceSettings
from t2_agentic_voice.evals import OverlapReplay, OverlapRequest
from t2_agentic_voice.ports import (
    AudioClip,
    ChatEvent,
    ChatModel,
    ChatRequest,
    Done,
    SpeechToText,
    TextDelta,
    Usage,
)

from tests.ole5_voice.evals.eot_support import Lines, parts_of, paused
from tests.ole5_voice.evals.fakes import FAKE_FLOW
from tests.ole5_voice.evals.run_support import FakeClock, World, golden_set, make_world
from tests.ole5_voice.evals.samples import WHEN

DIGEST = "d" * 64


def overlap(
    item: str,
    kind: Kind = "listening_sound",
    *,
    expected: Action = "go_on",
    reason: str | None = "short_output",
    action: Action = "go_on",
    words: str | None = "made-up words",
    failure: str | None = None,
    language: str = "saudi",
) -> OverlapResult:
    """One stored overlap of `kind`, decided by its window's request with `words`, `reason` and
    `action`; its deciding request failed with `failure` when given."""
    heard = Heard(
        turn_id=0, part="window", sent_ms=500.0, audio_s=0.75, text=words, failure=failure
    )
    other = Heard(turn_id=0, part="overlap", sent_ms=900.0, audio_s=1.0, text="other words")
    verdict = Verdict(
        opened=True,
        overlap_turns=(0,),
        action=action,
        reason=reason,
        decided_by="window",
        decided_turn=0,
        requests=(heard, other),
    )
    return OverlapResult.model_validate(
        {
            "item": item,
            "variant": f"{item}-laptop",
            "split": "dev",
            "kind": kind,
            "language": language,
            "device": "laptop",
            "expected": expected,
            "reply": ("the first clause.", "the second clause."),
            "reply_known": True,
            "verdict": verdict,
            "judged": judge(expected, verdict, None),
        }
    )


def stored(
    folder: Path,
    results: Sequence[OverlapResult],
    *,
    complete: bool = True,
    split: Split = "dev",
) -> Path:
    """A stored overlap run of `results`, written as `poe overlap` writes one (a held-out one's
    with its aggregates only)."""
    held_out = split == "held-out"
    run = OverlapRun(
        name="o1",
        started_at=WHEN,
        commit="c" * 40,
        answerer="pipeline",
        split=split,
        settings={"env": "dev"},
        data_digest=DIGEST,
        at_s=1.0,
        tail_s=4.5,
        stt_rpm=10,
        note="O1",
    )
    card = OverlapScorecard(
        run=run,
        complete=complete,
        totals=metrics(results),
        breakdowns=breakdowns(results, held_out=held_out),
        targets=targets(results, held_out=held_out),
        requests=2 * len(results),
        billed_seconds=20.0 * len(results),
        cost_usd=0.001,
        variants=() if held_out else tuple(results),
    )
    folder.mkdir(parents=True, exist_ok=True)
    (folder / SCORECARD_FILE).write_text(card.model_dump_json(), encoding="utf-8")
    return folder


# The steps the made-up rule decides by.
Reason = Literal["stop_word", "listening", "short_output"]


def made_up_rule(words: str) -> tuple[Action, Reason]:
    """A made-up rule on a window's words, as the revised one reads them: a stop word stops, as
    Whisper's «وكيف» for it does; «كامل» is a listening sound; anything else a short output."""
    if "وقف" in words or "وكيف" in words:
        return "stop", "stop_word"
    if "كامل" in words:
        return "go_on", "listening"
    return "go_on", "short_output"


@dataclass
class FakeAudioCall:
    """Stands in for `AudioCall`: each clip's call asks the speech-to-text it was built with for
    a window's and an overlap's transcripts (the call's `parts` by its number, where given),
    and the window's words decide by `rule`; a call whose number is in `fails` cannot be
    played. It keeps what each call was asked."""

    rule: Callable[[str], tuple[Action, Reason]] = made_up_rule
    parts: dict[int, tuple[Part, ...]] = field(default_factory=dict)
    fails: set[int] = field(default_factory=set)
    built: dict[str, Any] = field(default_factory=dict)
    played: list[dict[str, Any]] = field(default_factory=list)
    started: int = 0
    closed: int = 0

    def __call__(self, **built: Any) -> FakeAudioCall:
        self.built = built
        return self

    async def start(self) -> None:
        self.started += 1

    async def over_reply(
        self,
        clip: AudioClip,
        *,
        reply: Sequence[str],
        language: str,
        at_s: float,
        tail_s: float,
        word_end_ms: float | None = None,
    ) -> OverlapReplay:
        number = len(self.played)
        self.played.append({"clip": clip, "reply": tuple(reply), "language": language})
        if number in self.fails:
            raise ValueError("the reply is no phrase a greeting may say")
        stt: SpeechToText = self.built["stt"]
        parts = self.parts.get(number, ("window", "overlap"))
        heard = [await stt.transcribe(clip, language=None, prompt=None) for _ in parts]
        action, reason = self.rule(heard[0].text)
        requests = tuple(
            OverlapRequest(
                turn_id=0,
                part=part,
                sent_ms=500.0 * (k + 1),
                audio_s=0.75,
                text=found.text,
                no_speech_prob=found.no_speech_prob,
            )
            for k, (part, found) in enumerate(zip(parts, heard, strict=True))
        )
        return OverlapReplay(
            opened=True,
            overlap_turns=(0,),
            action=action,
            kind="false" if action == "go_on" else "stop",
            reason=reason,
            decided_by=parts[0],
            decided_turn=0,
            requests=requests,
        )

    async def aclose(self) -> None:
        self.closed += 1


Reply = str | ProviderError | BaseException | float


class FakeChat:
    """A `ChatModel` that answers each request from `script`: a text, streamed in two pieces
    with its usage; a `ProviderError` or another exception to raise; or a delay, in seconds of
    real time, before it says nothing. It keeps every request, and whether it was closed."""

    name = "fake-chat"
    data_flow = FAKE_FLOW

    def __init__(self, script: Sequence[Reply], clock: FakeClock, *, step_s: float = 0.1) -> None:
        self.script, self.clock, self.step_s = list(script), clock, step_s
        self.requests: list[ChatRequest] = []
        self.closed = False

    async def stream(self, request: ChatRequest) -> AsyncIterator[ChatEvent]:
        self.requests.append(request)
        reply = self.script.pop(0) if self.script else "go_on"
        if isinstance(reply, float):
            await asyncio.sleep(reply)
            reply = ""
        if isinstance(reply, BaseException):
            raise reply
        for piece in (reply[: len(reply) // 2], reply[len(reply) // 2 :]):
            self.clock.now += self.step_s
            if piece:
                yield TextDelta(text=piece)
        yield Usage(input_tokens=200, output_tokens=2, cached_tokens=100)
        yield Done(finish_reason="stop")

    async def aclose(self) -> None:
        self.closed = True


@dataclass
class URun:
    """A run's world: a checkout with its run worktree and golden set, the replay, the chat
    model, clock and history."""

    world: World
    chat: FakeChat
    clock: FakeClock
    lines: Lines = field(default_factory=Lines)
    built: list[VoiceSettings] = field(default_factory=list)
    items: dict[str, Item] = field(default_factory=dict)
    audio: FakeAudioCall = field(default_factory=FakeAudioCall)

    def store(self, name: str, results: Sequence[OverlapResult], **kept: Any) -> Path:
        """A stored overlap run of `results` (`stored`), each one's item and recording put in
        the golden set."""
        for result in results:
            kind, language = result.kind, result.language
            self.items[result.item] = paused(self.world, result.item, kind=kind, language=language)
        return stored(self.world.main / "var" / "runs" / name, results, **kept)

    def parts(self) -> UncertainParts:
        """The run's parts; with no item stored, the golden set's own loaders, which a run
        refused before it reads the golden set never calls."""
        plan = (
            parts_of(self.world, golden_set(*self.items.values()))
            if self.items
            else Parts(folder=self.world.top, git=self.world.git, now=lambda: WHEN)
        )
        plan = type(plan)(**{**plan.__dict__, "clock": self.clock, "sleep": self.clock.sleep})

        def chat_model(settings: VoiceSettings) -> ChatModel:
            self.built.append(settings)
            return self.chat

        return UncertainParts(
            plan=plan, chat_model=chat_model, audio_call=self.audio, append_line=self.lines
        )

    @property
    def out(self) -> Path:
        return self.world.main / "var" / "runs" / "u1"

    def argv(self, source: Path, *extra: str) -> list[str]:
        return [
            "--overlaps",
            str(source),
            "--model",
            "llama-3.1-8b-instant",
            "--reasoning-effort",
            "low",
            "--max-output-tokens",
            "16",
            "--timeout-s",
            "5",
            "--price-input",
            "0.05",
            "--price-output",
            "0.08",
            "--cap-usd",
            "1",
            "--day-requests",
            "1000",
            "--audio",
            f"owner={self.world.audio}",
            "--out",
            str(self.out),
            "--note",
            "U1 on O1",
            *extra,
        ]


def u_run(tmp_path: Path, *script: Reply) -> URun:
    clock = FakeClock()
    return URun(make_world(tmp_path), FakeChat(script, clock), clock)
