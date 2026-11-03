"""What the runner's tests share (`test_run*.py`, `test_answerers.py`, `test_worktree.py`,
`test_reference_answerer.py`): a fake `git`, a temporary checkout with a run worktree and an
audio root, made-up items, a clock that moves only when the run pauses, and a whole run's world
with the fakes it is built from. The `world` fixture is in `conftest.py`; each test starts
from the library's console logging (the suite's `_default_logging`)."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from ole5_voice.evals import run
from ole5_voice.evals.audio import sha256_of, write_wav
from ole5_voice.evals.models import AudioRef, Confirmation, Item, Language, SplitFile, Variant
from ole5_voice.evals.run_parts import DATA, Parts
from ole5_voice.evals.runs import VariantResult
from ole5_voice.evals.worktree import GitResult
from t2_agentic_voice import VoiceSettings
from t2_agentic_voice.ports import SpeechToText

from tests.ole5_voice.evals.fakes import (
    FakeGoldenSet,
    FakeHistory,
    FakeMatcher,
    FakeScorecardWriter,
    FakeSpeechToText,
    FakeTracing,
    fake_normalize,
)
from tests.ole5_voice.evals.samples import WHEN

COMMIT = "ab" * 20
# A run's flags with the reference answerer, which sends nothing; each case adds its own.
DEV = ["--answerer", "reference", "--split", "dev", "--out", "x", "--note", "n"]
HELD_OUT = ["--answerer", "reference", "--split", "held-out", "--out", "x", "--note", "n"]


@dataclass
class FakeGit:
    """A `Git` that answers the commands `worktree.py` asks, for a run worktree `top` linked to
    the checkout `main` (or the main checkout itself, when `top` is `main`)."""

    top: Path
    main: Path
    dirty: bool = False
    ignored: tuple[Path, ...] = ()  # folders whose paths git ignores, in the main checkout
    commit: str = COMMIT
    failing: tuple[str, ...] = ()  # commands that fail, by their first word after options
    calls: list[tuple[tuple[str, ...], Path]] = field(default_factory=list)

    def __call__(self, args: Sequence[str], cwd: Path) -> GitResult:
        command = tuple(args)
        self.calls.append((command, cwd))
        verb = next(word for word in command if not word.startswith("-"))
        if verb in self.failing:
            return GitResult(128, "")
        if command[:2] == ("rev-parse", "--path-format=absolute"):
            return GitResult(0, f"{self.top.as_posix()}\n")
        if command[:2] == ("worktree", "list"):
            trees = [self.main] + ([self.top] if self.top != self.main else [])
            return GitResult(
                0, "".join(f"worktree {t.as_posix()}\0HEAD {COMMIT}\0\0" for t in trees)
            )
        if command[:2] == ("rev-parse", "--verify"):
            return GitResult(0, f"{self.commit}\n")
        if verb == "status":
            return GitResult(0, " M apps/x.py\0" if self.dirty else "")
        if verb == "check-ignore":
            path = Path(command[-1])
            inside = any(path.is_relative_to(i.resolve()) for i in self.ignored)
            return GitResult(0 if inside else 1, "")
        raise AssertionError(f"git {command} is not faked")


class FakeClock:
    """Seconds that pass only when the run pauses, each pause recorded."""

    def __init__(self) -> None:
        self.now = 1000.0
        self.pauses: list[float] = []

    def __call__(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        self.pauses.append(seconds)
        self.now += seconds


@dataclass
class World:
    """A main checkout with a run worktree in it, the golden set's folder there, and an audio
    root `owner` outside them; `git` answers for it."""

    main: Path
    top: Path
    audio: Path
    git: FakeGit

    @property
    def data(self) -> Path:
        return self.top / DATA

    def clip(self, name: str, seconds: float = 1.0) -> AudioRef:
        wav = write_wav(b"\x10\x00" * int(16_000 * seconds))
        (self.audio / f"{name}.wav").write_bytes(wav)
        return AudioRef(root="owner", path=f"{name}.wav", sha256=sha256_of(wav))

    def item(
        self,
        item_id: str,
        text: str = "open the inbox",
        *,
        language: Language = "english",
        talkover: bool = False,
        takes: int = 1,
        segments: int = 1,
        seconds: float = 1.0,
        alternatives: tuple[str, ...] = (),
        confirmed: bool = True,  # each variant confirmed by the owner's listen, as a run needs
    ) -> Item:
        variants = tuple(
            Variant(
                id=f"{item_id}-v{n}",
                segments=tuple(self.clip(f"{item_id}-v{n}-s{k}", seconds) for k in range(segments)),
                device="laptop",
                session="s1",
                reference=text,
                reference_source="script" if text else "none",
                confirmations=(Confirmation(at=WHEN, review_pass=1),) if confirmed else (),
            )
            for n in range(1, takes + 1)
        )
        return Item(
            id=item_id,
            source="talkover" if talkover else "script",
            kind="request",
            language=language,
            text=text,
            alternatives=alternatives,
            terms=("Outlook",),
            want="send" if talkover else None,
            variants=variants,
        )


def make_world(tmp_path: Path) -> World:
    main, audio = tmp_path / "main", tmp_path / "audio"
    top = main / ".claude" / "worktrees" / "run"
    (top / DATA).mkdir(parents=True)
    audio.mkdir()
    (top / DATA / "spelling.toml").write_text("# made up\n", encoding="utf-8")
    return World(main, top, audio, FakeGit(top, main, ignored=(main / "var",)))


def golden_set(*found: Item, held_out: tuple[str, ...] = ()) -> FakeGoldenSet:
    sides = {i.id: "held-out" if i.id in held_out else "dev" for i in found}
    return FakeGoldenSet(found, SplitFile.model_validate({"salt": "m1", "items": sides}))


def plan_parts(golden: FakeGoldenSet) -> Parts:
    """A plan's parts: `golden`'s loaders and a fake matcher."""
    return Parts(
        load_items=golden.load_items,
        load_split=golden.load_split,
        load_matcher=lambda path: FakeMatcher(),
    )


class Setup:
    """A run's world and the fakes it is built from, to read back after `main`."""

    def __init__(
        self,
        tmp_path: Path,
        build: Callable[[World], tuple[Item, ...]] | None = None,
        held_out: tuple[str, ...] = (),
    ) -> None:
        world = self.world = make_world(tmp_path)
        found = build(world) if build else (world.item("a"), world.item("b", takes=2))
        self.golden = golden_set(*found, held_out=held_out)
        self.stt: SpeechToText = FakeSpeechToText()
        self.writer, self.history = FakeScorecardWriter(), FakeHistory()
        self.tracing, self.clock = FakeTracing(), FakeClock()
        self.adapter: Callable[[VoiceSettings], SpeechToText] | None = None  # by default, `stt`

    def parts(self) -> Parts:
        return Parts(
            folder=self.world.top,
            git=self.world.git,
            load_items=self.golden.load_items,
            load_split=self.golden.load_split,
            load_matcher=lambda path: FakeMatcher(),
            write_scorecard=self.writer,
            append_line=self.history,
            speech_to_text=self.adapter or (lambda settings: self.stt),
            tracing=lambda settings: self.tracing,
            normalize=fake_normalize,
            now=lambda: WHEN,
            clock=self.clock,
            sleep=self.clock.sleep,
        )

    def out(self, name: str = "r1") -> Path:
        return self.world.main / "var" / "runs" / name

    def main(self, *extra: str, answerer: str = "groq", split: str = "dev", out: str = "r1") -> int:
        argv = ["--answerer", answerer, "--split", split, "--out", str(self.out(out))]
        argv += ["--note", "a made-up run", "--audio", f"owner={self.world.audio}"]
        if answerer == "groq":
            argv += ["--price-per-hour", "0.111", "--cap-usd", "1"]
            argv += ["--model", "whisper-large-v3", "--timeout-s", "6"]
        return run.main([*argv, *extra], parts=self.parts())

    def results(self) -> tuple[VariantResult, ...]:
        ((_, results, _, _),) = self.writer.calls
        return results

    def calls(self) -> int:
        """How many requests reached the fake speech-to-text."""
        stt = self.stt
        assert isinstance(stt, FakeSpeechToText)
        return len(stt.calls)
