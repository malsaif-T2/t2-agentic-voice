"""The pieces of a run (`run_parts.py`): its plan of variants, each with its checked audio, the
smoke test's variant and the data's digest; the clip answers of `--clips-from`; each variant's
result; and the progress lines. Also the builders the runner's tests share: a temporary checkout
with an audio root, made-up items, and a clock that moves only when the run pauses."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pytest
from ole5_voice.evals import history, items, matcher, run_parts, scorecard, split
from ole5_voice.evals.audio import sha256_of, write_wav
from ole5_voice.evals.models import AudioRef, Confirmation, Item, Language, SplitFile, Variant
from ole5_voice.evals.run_parts import (
    DATA,
    Choice,
    Parts,
    Progress,
    audio_roots,
    clip_answers,
    is_name,
    load_plan,
)
from ole5_voice.evals.runs import Answer, Metrics, Request, Scorecard, SegmentAnswer
from t2_agentic_voice import InvalidRequestError, configure_logging

from tests.ole5_voice.evals import samples
from tests.ole5_voice.evals.fakes import FakeGoldenSet, FakeMatcher
from tests.ole5_voice.evals.test_worktree import FakeGit

WHEN = datetime(2026, 11, 3, 9, 0, tzinfo=UTC)


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


def _parts(golden: FakeGoldenSet) -> Parts:
    return Parts(
        load_items=golden.load_items,
        load_split=golden.load_split,
        load_matcher=lambda path: FakeMatcher(),
    )


@pytest.fixture(autouse=True)
def _plain_logs() -> None:
    configure_logging("INFO", "console")  # lines read as plain text, whatever ran before


@pytest.fixture
def world(tmp_path: Path) -> World:
    return make_world(tmp_path)


def test_a_plan_takes_its_splits_variants_each_with_its_checked_audio(world: World) -> None:
    golden = golden_set(
        world.item("a", takes=2),
        world.item("b", language="saudi"),
        world.item("h"),
        held_out=("h",),
    )
    plan = load_plan(
        world.data, Choice("dev", roots={"owner": world.audio}, needs_audio=True), _parts(golden)
    )
    assert [(t.item.id, t.variant.id) for t in plan.todo] == [
        ("a", "a-v1"),
        ("a", "a-v2"),
        ("b", "b-v1"),
    ]
    assert plan.smoke == plan.todo[0]
    assert [t.request.language for t in plan.todo] == ["en", "en", "ar"]
    assert plan.todo[2].request.segments == (world.audio / "b-v1-s0.wav",)
    assert golden.read == [world.data / "golden", world.data / "split.json"]
    auto = load_plan(world.data, Choice("dev", hint="auto"), _parts(golden))
    assert {t.request.language for t in auto.todo} == {None}
    assert auto.todo[0].request.segments == (Path("owner", "a-v1-s0.wav"),)  # named, never read


def test_a_held_out_plans_smoke_test_is_a_dev_variant(world: World) -> None:
    golden = golden_set(world.item("a"), world.item("h1"), world.item("h2"), held_out=("h1", "h2"))
    plan = load_plan(world.data, Choice("held-out"), _parts(golden))
    assert ([t.item.id for t in plan.todo], plan.smoke.item.id) == (["h1", "h2"], "a")
    with pytest.raises(InvalidRequestError, match="no dev variant for its smoke test"):
        load_plan(
            world.data, Choice("held-out"), _parts(golden_set(world.item("h"), held_out=("h",)))
        )


def test_a_windows_plan_takes_the_talkover_clips_and_its_smoke_test_sends_the_clip(
    world: World,
) -> None:
    golden = golden_set(world.item("n"), world.item("t", talkover=True))
    plan = load_plan(world.data, Choice("dev", windows_ms=(500, 750)), _parts(golden))
    assert [t.item.id for t in plan.todo] == ["t"]
    assert (plan.todo[0].request.windows_ms, plan.smoke.request.windows_ms) == ((500, 750), ())


def test_a_screen_file_narrows_a_dev_plan(world: World, tmp_path: Path) -> None:
    golden = golden_set(world.item("a", takes=2), world.item("b"))
    screen = tmp_path / "screen.txt"
    screen.write_text("b/b-v1\n\n a/a-v2 \n", encoding="utf-8")
    plan = load_plan(world.data, Choice("dev", questions=screen), _parts(golden))
    assert [t.variant.id for t in plan.todo] == ["a-v2", "b-v1"]
    screen.write_text("a/a-v9\nc/c-v1\n", encoding="utf-8")
    with pytest.raises(InvalidRequestError, match="names 2 variant"):
        load_plan(world.data, Choice("dev", questions=screen), _parts(golden))
    with pytest.raises(InvalidRequestError, match="--questions cannot be read"):
        load_plan(world.data, Choice("dev", questions=tmp_path / "none.txt"), _parts(golden))
    screen.write_text("", encoding="utf-8")
    with pytest.raises(InvalidRequestError, match="the run has no variant"):
        load_plan(world.data, Choice("dev", questions=screen), _parts(golden))


@pytest.mark.parametrize("damage", ["no root", "missing", "not a wav", "another file"])
def test_audio_that_is_not_its_manifests_file_is_refused_naming_no_variant(
    world: World, damage: str
) -> None:
    golden = golden_set(world.item("secret-item"))
    path = world.audio / "secret-item-v1-s0.wav"
    if damage == "missing":
        path.unlink()
    elif damage == "not a wav":
        path.write_bytes(b"RIFF....not audio")
    elif damage == "another file":
        path.write_bytes(write_wav(b"\x00\x00" * 160))
    roots = {} if damage == "no root" else {"owner": world.audio}
    with pytest.raises(InvalidRequestError) as refused:
        load_plan(world.data, Choice("dev", roots=roots, needs_audio=True), _parts(golden))
    assert "owner" in refused.value.message and "secret" not in refused.value.message


def test_a_golden_set_that_does_not_load_or_a_stale_split_is_refused(world: World) -> None:
    golden = golden_set(world.item("a"))

    def broken(folder: Path) -> tuple[Item, ...]:
        raise ValueError("a made-up parse error")

    with pytest.raises(InvalidRequestError, match="do not load"):
        load_plan(world.data, Choice("dev"), Parts(load_items=broken, load_split=golden.load_split))
    stale = FakeGoldenSet(golden.items, SplitFile(salt="m1", items={"a": "dev", "gone": "dev"}))
    with pytest.raises(InvalidRequestError, match="does not hold exactly"):
        load_plan(world.data, Choice("dev"), _parts(stale))
    (world.data / "spelling.toml").unlink()
    with pytest.raises(InvalidRequestError, match="do not load"):
        load_plan(world.data, Choice("dev"), _parts(golden))


def test_the_digest_covers_the_variants_the_split_and_the_spelling_guide(world: World) -> None:
    a, b = world.item("a"), world.item("b")

    def digest(*found: Item, held_out: tuple[str, ...] = ()) -> str:
        return load_plan(
            world.data, Choice("dev"), _parts(golden_set(*found, held_out=held_out))
        ).digest

    first = digest(a, b)
    assert len(first) == 64 and digest(a, b) == first
    assert digest(a, world.item("b", "open the outbox")) != first
    assert digest(a, b, world.item("h"), held_out=("h",)) != first  # the split changed
    (world.data / "spelling.toml").write_text("# another ruling\n", encoding="utf-8")
    assert digest(a, b) != first


def test_audio_roots_are_named_once(tmp_path: Path) -> None:
    assert audio_roots([f"talkover={tmp_path}", "owner=~/x"]) == {
        "talkover": tmp_path,
        "owner": Path("~/x").expanduser(),
    }
    for bad in (["owner"], ["owner="], ["=x"], ["Owner=x"], ["owner=a", "owner=b"]):
        with pytest.raises(InvalidRequestError, match="ROOT=FOLDER"):
            audio_roots(bad)
    assert (is_name("r1-large-v3"), is_name("R1"), is_name("")) == (True, False, False)


def _card(world: World, *, model: str = "whisper-large-v3", commit: str = "ab" * 20) -> Path:
    first, second = samples.result("a-v1", heard="open"), samples.result("b-v1", heard="x y")
    split_answer = second.answer.model_copy(
        update={"segments": (SegmentAnswer(text="x"), SegmentAnswer(text="y"))}
    )
    rows = [
        first.model_copy(update={"item": "a"}),
        second.model_copy(update={"item": "b", "answer": split_answer}),
    ]
    run = samples.run().model_copy(update={"model": model, "commit": commit})
    path = world.top.parent / f"card-{model}.json"
    path.write_text(
        Scorecard(
            run=run,
            complete=True,
            totals=Metrics(items=2, variants=2, right=1, failures=0),
            breakdowns={},
            variants=tuple(rows),
        ).model_dump_json(),
        encoding="utf-8",
    )
    return path


def test_clips_from_gives_the_first_segments_answer_of_the_same_model_at_this_commit(
    world: World,
) -> None:
    golden = golden_set(world.item("a"), world.item("b"), world.item("c"))
    todo = load_plan(world.data, Choice("dev"), _parts(golden)).todo
    found = clip_answers(_card(world), todo, commit="ab" * 20, model="whisper-large-v3")
    assert found == {todo[0].variant: "open", todo[1].variant: "x"}
    assert clip_answers(None, todo, commit="ab" * 20, model="whisper-large-v3") == {}
    with pytest.raises(InvalidRequestError, match="not a dev run of this model at this commit"):
        clip_answers(_card(world), todo, commit="cd" * 20, model="whisper-large-v3")
    with pytest.raises(InvalidRequestError, match="not a dev run of this model"):
        clip_answers(_card(world), todo, commit="ab" * 20, model="whisper-large-v3-turbo")
    with pytest.raises(InvalidRequestError, match="not a scorecard"):
        clip_answers(world.data / "spelling.toml", todo, commit="ab" * 20, model="x")


def test_a_result_is_judged_by_the_matcher_on_the_reference_and_its_alternatives(
    world: World,
) -> None:
    golden = golden_set(world.item("a", "open the inbox", alternatives=("open my inbox",)))
    todo = load_plan(world.data, Choice("dev"), _parts(golden)).todo[0]
    judge = FakeMatcher()

    def judged(answer: Answer, judged: bool = True) -> bool | None:
        return todo.result(answer, judge, "dev", judged).right

    assert judged(Answer(variant="a-v1", text="Open my inbox!")) is True
    assert judged(Answer(variant="a-v1", text="open")) is False
    assert judged(Answer(variant="a-v1", failure="provider")) is None
    assert judged(Answer(variant="a-v1"), judged=False) is None
    assert judge.calls[0] == ("Open my inbox!", ("open the inbox", "open my inbox"))
    result = todo.result(Answer(variant="a-v1", text="x"), judge, "dev", True)
    assert (result.terms, result.want, result.tags, result.kind) == (
        ("Outlook",),
        None,
        (),
        "request",
    )


def test_a_dev_runs_progress_lines_carry_identifiers_and_verdicts_never_text(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    clock, file = FakeClock(), tmp_path / "results.jsonl"
    progress = Progress(total=3, results_file=file, clock=clock, began=clock())
    retried = (
        Request(segment=0, attempt=1, latency_ms=5, billed_seconds=10, outcome="timeout"),
        Request(segment=0, attempt=2, latency_ms=7, billed_seconds=10, outcome="ok"),
    )
    progress.add(
        samples.result("v1", heard="zebra quartz", right=False).model_copy(
            update={"answer": Answer(variant="v1", text="zebra quartz", requests=retried)}
        )
    )
    clock.now += 2.5
    progress.add(
        samples.result("v2").model_copy(
            update={"answer": Answer(variant="v2", failure="stuck"), "right": None}
        )
    )
    out = capsys.readouterr().out
    assert "verdict=wrong" in out and "retries=1" in out and "latency_ms=12" in out
    assert "verdict=stuck" in out and "elapsed_s=2.5" in out and "variant=v2" in out
    assert "zebra" not in out and "stop now" not in out
    assert [line.count('"variant"') for line in file.read_text(encoding="utf-8").splitlines()] == [
        2,
        2,
    ]


def test_a_held_out_runs_progress_lines_are_counts_only(
    capsys: pytest.CaptureFixture[str],
) -> None:
    clock = FakeClock()
    progress = Progress(total=2, results_file=None, clock=clock, began=clock())
    progress.add(samples.result("secret-v1").model_copy(update={"item": "secret-item"}))
    out = capsys.readouterr().out
    assert "done=1" in out and "of=2" in out
    assert "secret" not in out and "right" not in out and "verdict" not in out


def test_the_parts_default_to_the_real_pieces(monkeypatch: pytest.MonkeyPatch) -> None:
    parts = Parts()
    assert (parts.load_items, parts.load_split, parts.load_matcher) == (
        items.load_items,
        split.load_split,
        matcher.load_matcher,
    )
    assert (parts.write_scorecard, parts.append_line) == (
        scorecard.write_scorecard,
        history.append_line,
    )
    assert parts.folder == Path(run_parts.__file__).resolve().parent
    assert parts.now().tzinfo is UTC
    monkeypatch.setattr(run_parts, "normalize_arabic", lambda text: f"arabic({text})")
    monkeypatch.setattr(run_parts, "normalize_digits", lambda text: f"digits({text})")
    assert run_parts.canonical("x") == "digits(arabic(x))"  # the digits after the letters
