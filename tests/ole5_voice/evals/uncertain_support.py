"""What the tests of `poe uncertain` share (test_uncertain*.py): made-up stored overlap runs, a
fake chat model that answers from a script and keeps every request, and a run's world (a
checkout with a run worktree, a clock that moves only when the run pauses, the history lines)."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from ole5_voice.evals.models import Kind, Split
from ole5_voice.evals.overlap_card import OverlapRun, OverlapScorecard, breakdowns
from ole5_voice.evals.overlap_score import (
    Action,
    Heard,
    OverlapResult,
    Verdict,
    judge,
    metrics,
    targets,
)
from ole5_voice.evals.run_parts import Parts
from ole5_voice.evals.runs import SCORECARD_FILE
from ole5_voice.evals.uncertain import UncertainParts
from t2_agentic_voice import ProviderError, VoiceSettings
from t2_agentic_voice.ports import ChatEvent, ChatModel, ChatRequest, Done, TextDelta, Usage

from tests.ole5_voice.evals.eot_support import Lines
from tests.ole5_voice.evals.fakes import FAKE_FLOW
from tests.ole5_voice.evals.run_support import FakeClock, World, make_world
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
    """A run's world: a checkout with its run worktree, the chat model, clock and history."""

    world: World
    chat: FakeChat
    clock: FakeClock
    lines: Lines = field(default_factory=Lines)
    built: list[VoiceSettings] = field(default_factory=list)

    def parts(self) -> UncertainParts:
        plan = Parts(
            folder=self.world.top,
            git=self.world.git,
            now=lambda: WHEN,
            clock=self.clock,
            sleep=self.clock.sleep,
        )

        def chat_model(settings: VoiceSettings) -> ChatModel:
            self.built.append(settings)
            return self.chat

        return UncertainParts(plan=plan, chat_model=chat_model, append_line=self.lines)

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
            "--out",
            str(self.out),
            "--note",
            "U1 on O1",
            *extra,
        ]


def u_run(tmp_path: Path, *script: Reply) -> URun:
    clock = FakeClock()
    return URun(make_world(tmp_path), FakeChat(script, clock), clock)
