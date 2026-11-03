"""What the tests of `poe overlap` share (test_overlap.py, test_overlap_run.py): made-up overlap
clips in a run's world (`run_support.World`), a fake replay that answers each clip from a script
and keeps what it was asked, and the parts a run is built from, its clock moving only when the
run pauses."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from ole5_voice.evals.models import Confirmation, Device, Item, Language, Variant
from ole5_voice.evals.overlap import OverlapParts
from ole5_voice.evals.run_parts import Parts
from t2_agentic_voice import VoiceSettings
from t2_agentic_voice.evals import OverlapReplay, OverlapRequest
from t2_agentic_voice.ports import AudioClip, SpeechToText

from tests.ole5_voice.evals.eot_support import Lines
from tests.ole5_voice.evals.fakes import FakeGoldenSet, FakeMatcher, FakeSpeechToText
from tests.ole5_voice.evals.run_support import FakeClock, World
from tests.ole5_voice.evals.samples import WHEN

# A script that has the made-up script items' lines (`clip(..., source="script")`), one of
# them said over the lab's reply `r1`.
SCRIPT = """listening_sounds = []

[[lines]]
id = "k1"
kind = "stop_word"
language = "saudi"
say = ["made-up"]

[[lines]]
id = "q1"
kind = "echo_only"
language = "none"
reply = "r1"
"""


def clip(
    world: World,
    item_id: str,
    kind: str,
    *,
    language: Language = "saudi",
    tags: tuple[str, ...] = (),
    devices: tuple[Device, ...] = ("laptop",),
    end_ms: int | None = None,
    source: str = "talkover",
    seconds: float = 1.0,
) -> Item:
    """An item of `kind` with one confirmed variant per device, each `seconds` long, tagged
    `tags`, its word's end marked at `end_ms` when given."""
    text = "" if language == "none" else "made-up"
    variants = tuple(
        Variant(
            id=f"{item_id}-{device}",
            segments=(world.clip(f"{item_id}-{device}", seconds),),
            device=device,
            session=f"{device}-1",
            reference=text,
            reference_source="script" if text else "none",
            confirmations=(Confirmation(at=WHEN, review_pass=1),),
            turn_ends_ms=() if end_ms is None else (end_ms,),
            tags=tags,
        )
        for device in devices
    )
    found: dict[str, Any] = {"id": item_id, "source": source, "kind": kind, "text": text}
    return Item.model_validate(found | {"language": language, "variants": variants})


# The parts of an overlap, in the order their requests go.
PARTS: tuple[Literal["window", "overlap"], ...] = ("window", "overlap")


def stop(
    requests: int = 2, *, last_ms: float = 1600.0, failure: str | None = None
) -> OverlapReplay:
    """A replay that stopped the agent, decided by `requests` requests, the last frame at
    `last_ms`, each request failing with `failure` when given."""
    heard = tuple(
        OverlapRequest(
            part=part,
            sent_ms=500.0,
            answered_ms=800.0,
            audio_s=0.75,
            text="made-up",
            failure=failure,  # type: ignore[arg-type]
        )
        for part in PARTS[:requests]
    )
    return OverlapReplay(
        opened=True,
        action="stop",
        kind="stop",
        reason="stop_word",
        decided_by="window",
        requests=heard,
        speech_stop_ms=1100.0,
        last_audio_ms=last_ms,
    )


WENT_ON = OverlapReplay(opened=True, action="go_on", kind="false", reason="listening")


@dataclass
class FakeReplayer:
    """Stands in for `AudioCall`: each clip answered by the next of `script` (a replay, or an
    exception to raise), keeping what it was built with and asked, and when (on `clock`), and
    whether it was started and closed."""

    script: list[OverlapReplay | BaseException]
    clock: FakeClock
    built: dict[str, Any] = field(default_factory=dict)
    asked: list[dict[str, Any]] = field(default_factory=list)
    started: int = 0
    closed: int = 0

    def __call__(self, **built: Any) -> FakeReplayer:
        self.built = built
        return self

    async def start(self) -> None:
        self.started += 1

    async def over_reply(self, clip: AudioClip, **asked: Any) -> OverlapReplay:
        tts = self.built["tts"]
        self.asked.append({"clip": clip, "at": self.clock.now, "seconds": tts.seconds, **asked})
        answer = self.script.pop(0)
        if isinstance(answer, BaseException):
            raise answer
        return answer

    async def aclose(self) -> None:
        self.closed += 1


@dataclass
class Run:
    """A run's world: its parts, its replay, speech-to-text, clock and history lines."""

    world: World
    golden: FakeGoldenSet
    replayer: FakeReplayer
    stt: FakeSpeechToText = field(default_factory=FakeSpeechToText)
    lines: Lines = field(default_factory=Lines)
    clock: FakeClock = field(default_factory=FakeClock)

    def parts(self) -> OverlapParts:
        plan = Parts(
            folder=self.world.top,
            git=self.world.git,
            load_items=self.golden.load_items,
            load_split=self.golden.load_split,
            load_matcher=lambda path: FakeMatcher(),
            now=lambda: WHEN,
            clock=self.clock,
            sleep=self.clock.sleep,
        )

        def stt(settings: VoiceSettings) -> SpeechToText:
            return self.stt

        return OverlapParts(
            plan=plan, speech_to_text=stt, audio_call=self.replayer, append_line=self.lines
        )

    @property
    def out(self) -> Path:
        return self.world.main / "var" / "runs" / "o1"


def pipeline(run: Run, *extra: str, split: str = "dev") -> list[str]:
    """A pipeline run's flags in `run`'s world."""
    return [
        "--answerer",
        "pipeline",
        "--split",
        split,
        "--out",
        str(run.out),
        "--note",
        "O1",
        "--audio",
        f"owner={run.world.audio}",
        "--model",
        "whisper-large-v3",
        "--timeout-s",
        "6",
        "--price-per-hour",
        "0.111",
        "--cap-usd",
        "5",
        *extra,
    ]


def requests_in_any_minute(times: Sequence[float], counts: Sequence[int]) -> int:
    """The most requests counted in any 60 s, each call's counted at its start."""
    return max(
        sum(n for t, n in zip(times, counts, strict=True) if start <= t < start + 60)
        for start in times
    )
