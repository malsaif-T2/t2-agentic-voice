"""The pieces of a run (`run_parts.py`): its plan of variants, each with its checked audio, the
smoke test's variant and the data's digest; the clip answers of `--clips-from`; each variant's
result; and the progress lines. The builders it shares with the runner's other tests are in
`run_support.py`."""

from __future__ import annotations

from datetime import UTC
from pathlib import Path

import pytest
from ole5_voice.evals import history, items, matcher, run_parts, scorecard, split
from ole5_voice.evals.audio import write_wav
from ole5_voice.evals.models import Item, SplitFile
from ole5_voice.evals.run_parts import (
    Choice,
    Parts,
    Progress,
    audio_roots,
    clip_answers,
    is_name,
    load_plan,
)
from ole5_voice.evals.runs import Answer, Metrics, Request, Scorecard, SegmentAnswer
from t2_agentic_voice import InvalidRequestError

from tests.ole5_voice.evals import samples
from tests.ole5_voice.evals.fakes import FakeGoldenSet, FakeMatcher
from tests.ole5_voice.evals.run_support import FakeClock, World, golden_set, plan_parts

pytestmark = pytest.mark.usefixtures("plain_logs")


def test_a_plan_takes_its_splits_variants_each_with_its_checked_audio(world: World) -> None:
    golden = golden_set(
        world.item("a", takes=2),
        world.item("b", language="saudi"),
        world.item("h"),
        held_out=("h",),
    )
    plan = load_plan(
        world.data,
        Choice("dev", roots={"owner": world.audio}, needs_audio=True),
        plan_parts(golden),
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
    auto = load_plan(world.data, Choice("dev", hint="auto"), plan_parts(golden))
    assert {t.request.language for t in auto.todo} == {None}
    assert auto.todo[0].request.segments == (Path("owner", "a-v1-s0.wav"),)  # named, never read


def test_a_held_out_plans_smoke_test_is_a_dev_variant(world: World) -> None:
    golden = golden_set(world.item("a"), world.item("h1"), world.item("h2"), held_out=("h1", "h2"))
    plan = load_plan(world.data, Choice("held-out"), plan_parts(golden))
    assert ([t.item.id for t in plan.todo], plan.smoke.item.id) == (["h1", "h2"], "a")
    with pytest.raises(InvalidRequestError, match="no dev variant for its smoke test"):
        load_plan(
            world.data, Choice("held-out"), plan_parts(golden_set(world.item("h"), held_out=("h",)))
        )


def test_a_windows_plan_takes_the_talkover_clips_and_its_smoke_test_sends_the_clip(
    world: World,
) -> None:
    golden = golden_set(world.item("n"), world.item("t", talkover=True))
    plan = load_plan(world.data, Choice("dev", windows_ms=(500, 750)), plan_parts(golden))
    assert [t.item.id for t in plan.todo] == ["t"]
    assert (plan.todo[0].request.windows_ms, plan.smoke.request.windows_ms) == ((500, 750), ())


def test_a_screen_file_narrows_a_dev_plan(world: World, tmp_path: Path) -> None:
    golden = golden_set(world.item("a", takes=2), world.item("b"))
    screen = tmp_path / "screen.txt"
    screen.write_text("# a screen of two\nb/b-v1\n\n a/a-v2 \n", encoding="utf-8")
    plan = load_plan(world.data, Choice("dev", questions=screen), plan_parts(golden))
    assert [t.variant.id for t in plan.todo] == ["a-v2", "b-v1"]
    screen.write_text("a/a-v9\nc/c-v1\n", encoding="utf-8")
    with pytest.raises(InvalidRequestError, match="names 2 variant"):
        load_plan(world.data, Choice("dev", questions=screen), plan_parts(golden))
    with pytest.raises(InvalidRequestError, match="--questions cannot be read"):
        load_plan(world.data, Choice("dev", questions=tmp_path / "none.txt"), plan_parts(golden))
    screen.write_text("", encoding="utf-8")
    with pytest.raises(InvalidRequestError, match="the run has no variant"):
        load_plan(world.data, Choice("dev", questions=screen), plan_parts(golden))


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
        load_plan(world.data, Choice("dev", roots=roots, needs_audio=True), plan_parts(golden))
    assert "owner" in refused.value.message and "secret" not in refused.value.message


def test_a_golden_set_that_does_not_load_or_a_stale_split_is_refused(world: World) -> None:
    golden = golden_set(world.item("a"))

    def broken(folder: Path) -> tuple[Item, ...]:
        raise ValueError("a made-up parse error")

    with pytest.raises(InvalidRequestError, match="do not load"):
        load_plan(world.data, Choice("dev"), Parts(load_items=broken, load_split=golden.load_split))
    stale = FakeGoldenSet(golden.items, SplitFile(salt="m1", items={"a": "dev", "gone": "dev"}))
    with pytest.raises(InvalidRequestError, match="does not hold exactly"):
        load_plan(world.data, Choice("dev"), plan_parts(stale))
    (world.data / "spelling.toml").unlink()
    with pytest.raises(InvalidRequestError, match="do not load"):
        load_plan(world.data, Choice("dev"), plan_parts(golden))


def test_the_digest_covers_the_variants_the_split_and_the_spelling_guide(world: World) -> None:
    a, b = world.item("a"), world.item("b")

    def digest(*found: Item, held_out: tuple[str, ...] = ()) -> str:
        return load_plan(
            world.data, Choice("dev"), plan_parts(golden_set(*found, held_out=held_out))
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
    todo = load_plan(world.data, Choice("dev"), plan_parts(golden)).todo
    found = clip_answers(_card(world), todo, commit="ab" * 20, model="whisper-large-v3")
    assert found == {todo[0].variant: "open", todo[1].variant: "x"}
    run_folder = world.top.parent / "r1"
    run_folder.mkdir()
    _card(world).replace(run_folder / "scorecard.json")  # a run's --out folder serves as well
    assert clip_answers(run_folder, todo, commit="ab" * 20, model="whisper-large-v3") == found
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
    todo = load_plan(world.data, Choice("dev"), plan_parts(golden)).todo[0]
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
    assert parts.normalize is matcher.normalize  # the scorers' form (test_library_copies.py)
