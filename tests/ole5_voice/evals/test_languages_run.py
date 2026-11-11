"""`poe eval-languages` (plan 007's Block H, run H's H1; its scorer is test_languages_score.py's):
a pass through a fake `turn_languages` and a fake classifier, so no model loads and no time
passes: the settings and the classifier each pass gives the calls, the classifier loaded before
any clip and closed once; the turns written as each variant finishes, the scorecard and the
history line; a held-out pass's aggregates only, its turns kept whole for run H to read; the
smoke variant alone; `--read`, condition 4 across the passes; and the refusals before any clip
is fed."""

from __future__ import annotations

from collections.abc import AsyncIterator, Iterable, Sequence
from pathlib import Path
from typing import Any

import pytest
from ole5_voice.agent import ECHO_AGENT
from ole5_voice.evals import languages_run, languages_setup
from ole5_voice.evals.items import HISTORY_FILE
from ole5_voice.evals.languages_card import (
    TURNS_FILE,
    LanguageResult,
    LanguagesLine,
    LanguagesScorecard,
)
from ole5_voice.evals.run_parts import Parts
from ole5_voice.evals.runs import SCORECARD_FILE
from t2_agentic_voice import ConfigurationError, VoiceSettings
from t2_agentic_voice.evals import LanguageTurn
from t2_agentic_voice.ports import AudioClip, LanguageScores

from tests.ole5_voice.evals.eot_support import Lines, golden_set, parts_of, paused
from tests.ole5_voice.evals.languages_support import pass_folder, result, run_info, turn
from tests.ole5_voice.evals.run_support import World, make_world


class FakeTurnLanguages:
    """Stands in for `evals.turn_languages`: each clip's turns from a script, one entry a clip,
    keeping the clips, what it was asked and the classifier's loads by the time it was
    called."""

    def __init__(
        self, script: list[tuple[LanguageTurn, ...]], *, interrupt_after: int | None = None
    ) -> None:
        self.script, self.interrupt_after = script, interrupt_after
        self.clips: list[AudioClip] = []
        self.asked: dict[str, Any] = {}
        self.loaded_before: list[tuple[str, ...]] | None = None
        self.closed = False

    async def __call__(
        self, clips: Iterable[AudioClip], **asked: Any
    ) -> AsyncIterator[tuple[LanguageTurn, ...]]:
        self.clips, self.asked = list(clips), asked
        given = asked["classifier"]
        self.loaded_before = None if given is None else list(given.loaded)
        try:
            for number, turns in enumerate(self.script[: len(self.clips)]):
                if number == self.interrupt_after:
                    raise KeyboardInterrupt
                yield turns
        finally:
            self.closed = True


class FakeClassifier:
    """A classifier that records its loads and closes, or refuses to load."""

    name = "fake"

    def __init__(self, refuse: bool = False) -> None:
        self.refuse = refuse
        self.loaded: list[tuple[str, ...]] = []
        self.closed = 0

    async def load(self, among: Sequence[str]) -> None:
        if self.refuse:
            raise ConfigurationError("The classifier's files are missing. FIX: fetch them.")
        self.loaded.append(tuple(among))

    async def classify(self, clip: AudioClip, *, among: Sequence[str]) -> LanguageScores | None:
        raise AssertionError("the fake turn_languages classifies nothing")

    async def aclose(self) -> None:
        self.closed += 1


class Classifiers:
    """Stands in for building the classifier the settings name: keeps each settings given."""

    def __init__(self, made: FakeClassifier | None = None) -> None:
        self.made = made or FakeClassifier()
        self.settings: list[VoiceSettings] = []

    def __call__(self, settings: VoiceSettings) -> FakeClassifier:
        self.settings.append(settings)
        return self.made


def _world(tmp_path: Path) -> tuple[World, Parts]:
    world = make_world(tmp_path)
    found = (
        paused(world, "p1", devices=("laptop", "wired")),
        paused(world, "e1", language="english", kind="request"),
        paused(world, "n1", language="none", kind="noise", seconds=1.0),
    )
    return world, parts_of(world, golden_set(*found))


# p1-laptop's one turn ends before its mark (1500 ms): a cut-off; p1-wired's after it.
SCRIPT = [
    (turn("short", end_ms=1000.0),),
    (turn("short", end_ms=1700.0),),
    (turn(named="en"), turn("late", named="en")),
    (),
]


def _argv(world: World, *extra: str, classifier: str = "silero", split: str = "dev") -> list[str]:
    out = world.main / "var" / "runs" / "lid1-dev-silero"
    argv = ["--split", split, "--classifier", classifier, "--out", str(out), "--note", "H1"]
    argv += ["--audio", f"owner={world.audio}"]
    if classifier != "off":
        argv += ["--classifier-dir", str(world.main / "models")]
    return [*argv, *extra]


def _out(world: World) -> Path:
    return world.main / "var" / "runs" / "lid1-dev-silero"


def _main(
    argv: list[str],
    parts: Parts,
    fake: FakeTurnLanguages,
    classifiers: Classifiers | None = None,
    lines: Lines | None = None,
) -> int:
    return languages_run.main(
        argv,
        parts=parts,
        turn_languages=fake,
        make_classifier=classifiers or Classifiers(),
        append_line=lines or Lines(),
        peak=lambda: 321.5,
    )


def test_a_classifier_pass_feeds_each_variant_and_writes_as_it_goes(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    world, parts = _world(tmp_path)
    fake, classifiers, lines = FakeTurnLanguages(SCRIPT), Classifiers(), Lines()
    assert _main(_argv(world), parts, fake, classifiers, lines) == 0
    (built,) = classifiers.settings
    stt = built.stt
    assert (stt.live_language, stt.classifier, stt.classifier_dir) == (
        "classified",
        "silero",
        world.main / "models",
    )
    asked = fake.asked
    assert asked["settings"] is built and asked["classifier"] is classifiers.made
    assert asked["languages"] == ECHO_AGENT.languages
    assert (asked["lead_s"], asked["tail_s"]) == (1.0, 4.5)
    assert fake.loaded_before == [("ar", "en")] and classifiers.made.closed == 1
    out = _out(world)
    card = LanguagesScorecard.model_validate_json((out / SCORECARD_FILE).read_bytes())
    assert [r.variant for r in card.variants] == ["p1-laptop", "p1-wired", "e1-laptop", "n1-laptop"]
    assert (card.complete, card.run.classifier, card.run.held_in, card.run.peak_mb) == (
        True,
        "silero",
        "ar",
        321.5,
    )
    assert card.card.paused.cut_offs == 1 and card.card.calls["ar"].changed == 1
    assert card.run.settings["stt.classifier_from_s"] == "2.0"
    assert "stt.classifier_dir" not in card.run.settings
    turns = (out / TURNS_FILE).read_text("utf-8").splitlines()
    assert [LanguageResult.model_validate_json(t) for t in turns] == list(card.variants)
    ((line, first), (same, second)) = lines.appended
    assert line is same and isinstance(line, LanguagesLine)
    assert (first, second) == (world.data / HISTORY_FILE, out / HISTORY_FILE)
    assert (line.classifier, line.variants, line.cut_offs, line.in_time, line.late) == (
        "silero",
        4,
        1,
        1,
        1,
    )
    logged = capsys.readouterr().out
    assert "variant_done" in logged and "made-up" not in logged
    assert [len(clip.pcm16) for clip in fake.clips] == [64_000, 64_000, 64_000, 32_000]


def test_an_off_pass_builds_no_classifier_and_names_the_sessions_language(
    tmp_path: Path,
) -> None:
    world, parts = _world(tmp_path)
    fake, classifiers, lines = FakeTurnLanguages([(turn("session"),)] * 4), Classifiers(), Lines()
    assert _main(_argv(world, classifier="off"), parts, fake, classifiers, lines) == 0
    assert classifiers.settings == [] and fake.asked["classifier"] is None
    assert fake.asked["settings"].stt.live_language == "session"
    card = LanguagesScorecard.model_validate_json((_out(world) / SCORECARD_FILE).read_bytes())
    assert card.run.classifier == "off" and card.card.by == {"session": 4}
    assert card.run.settings["stt.classifier"] == "none"
    (line, _), _ = lines.appended
    assert isinstance(line, LanguagesLine) and line.classifier == "off"


def test_a_held_out_pass_keeps_aggregates_and_its_turns_whole_once_complete(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    world = make_world(tmp_path)
    found = [paused(world, f"h{n}") for n in range(3)]
    parts = parts_of(world, golden_set(*found, paused(world, "d1"), held_out=("h0", "h1", "h2")))
    fake = FakeTurnLanguages([(turn("short", end_ms=1700.0),)] * 3)
    assert _main(_argv(world, split="held-out"), parts, fake) == 0
    out = _out(world)
    card = LanguagesScorecard.model_validate_json((out / SCORECARD_FILE).read_bytes())
    assert card.variants == () and card.card.variants == 3
    assert len((out / TURNS_FILE).read_text("utf-8").splitlines()) == 3
    logged = capsys.readouterr().out
    assert "variant_done" not in logged and "h0" not in logged
    interrupted = make_world(tmp_path / "again")
    found = [paused(interrupted, f"h{n}") for n in range(3)]
    parts = parts_of(
        interrupted, golden_set(*found, paused(interrupted, "d1"), held_out=("h0", "h1", "h2"))
    )
    fake = FakeTurnLanguages([(turn("short"),)] * 3, interrupt_after=1)
    assert _main(_argv(interrupted, split="held-out"), parts, fake) == 1
    assert not (_out(interrupted) / TURNS_FILE).exists()


def test_an_interrupted_pass_keeps_what_it_measured_and_closes_its_classifier(
    tmp_path: Path,
) -> None:
    world, parts = _world(tmp_path)
    fake, classifiers = FakeTurnLanguages(SCRIPT, interrupt_after=2), Classifiers()
    assert _main(_argv(world), parts, fake, classifiers) == 1
    card = LanguagesScorecard.model_validate_json((_out(world) / SCORECARD_FILE).read_bytes())
    assert (card.complete, len(card.variants)) == (False, 2)
    assert fake.closed and classifiers.made.closed == 1


def test_the_smoke_variant_runs_alone_and_appends_no_line(tmp_path: Path) -> None:
    world, parts = _world(tmp_path)
    fake, lines = FakeTurnLanguages(SCRIPT), Lines()
    assert _main(_argv(world, "--smoke-only"), parts, fake, lines=lines) == 0
    card = LanguagesScorecard.model_validate_json((_out(world) / SCORECARD_FILE).read_bytes())
    assert [r.variant for r in card.variants] == ["p1-laptop"] and len(fake.clips) == 1
    assert card.run.settings["run.smoke_only"] == "true" and lines.appended == []


@pytest.mark.parametrize(
    ("change", "named"),
    [
        ({"main": True}, "this is the main checkout"),
        ({"dirty": True}, "the worktree has changes"),
    ],
)
def test_a_pass_refuses_the_main_checkout_and_a_dirty_tree_before_any_clip(
    tmp_path: Path, change: dict[str, bool], named: str, capsys: pytest.CaptureFixture[str]
) -> None:
    world, parts = _world(tmp_path)
    if change.get("main"):
        world.git.top = world.main
        parts = Parts(**{**parts.__dict__, "folder": world.main})
    world.git.dirty = change.get("dirty", False)
    fake, classifiers = FakeTurnLanguages([]), Classifiers()
    assert _main(_argv(world), parts, fake, classifiers) == 2
    assert named in capsys.readouterr().out and fake.clips == []
    assert classifiers.made.loaded == []


@pytest.mark.parametrize(
    ("variable", "value"),
    [
        ("T2V_STT__CLASSIFIER_FROM_S", "2.5"),
        ("T2V_STT__CLASSIFIER_MIN_SHARE", "0.6"),
        ("T2V_STT__CLASSIFIER_THREADS", "4"),
    ],
)
def test_a_pass_refuses_a_rule_other_than_the_registered_one(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    variable: str,
    value: str,
) -> None:
    world, parts = _world(tmp_path)
    monkeypatch.setenv(variable, value)
    fake = FakeTurnLanguages([])
    assert _main(_argv(world), parts, fake) == 2
    assert "stt.classifier_from_s 2.0" in capsys.readouterr().out and fake.clips == []
    assert not _out(world).exists()


def test_a_classifier_that_does_not_load_is_refused_before_any_clip(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    world, parts = _world(tmp_path)
    classifiers, fake = Classifiers(FakeClassifier(refuse=True)), FakeTurnLanguages([])
    assert _main(_argv(world), parts, fake, classifiers) == 2
    assert "files are missing" in capsys.readouterr().out
    assert fake.clips == [] and not _out(world).exists() and classifiers.made.closed == 1


def test_a_pass_refuses_a_paused_request_with_no_mark_and_a_bad_name(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    world = make_world(tmp_path)
    unmarked = paused(world, "p9")
    blank = unmarked.model_copy(
        update={"variants": (unmarked.variants[0].model_copy(update={"turn_ends_ms": ()}),)}
    )
    fake = FakeTurnLanguages([])
    assert _main(_argv(world), parts_of(world, golden_set(blank)), fake) == 2
    assert "no turn end marked" in capsys.readouterr().out
    world, parts = _world(tmp_path / "named")
    argv = _argv(world)
    argv[argv.index("--out") + 1] = str(world.main / "var" / "runs" / "Bad Name")
    assert _main(argv, parts, fake) == 2
    assert "is not a name" in capsys.readouterr().out and fake.clips == []


@pytest.mark.parametrize(
    ("argv", "named"),
    [
        (["--split", "dev", "--classifier", "off"], "a pass needs --out, --note"),
        (
            ["--split", "dev", "--classifier", "off", "--out", "x", "--note", "{{" + "X}}"],
            "placeholder",
        ),
        (["--read", "a", "b", "--split", "dev"], "--read takes the passes alone"),
        (
            [
                "--split",
                "held-out",
                "--classifier",
                "off",
                "--out",
                "x",
                "--note",
                "n",
                "--smoke-only",
            ],
            "--smoke-only is a dev",
        ),
    ],
)
def test_the_flags_a_pass_needs(
    argv: list[str], named: str, capsys: pytest.CaptureFixture[str]
) -> None:
    with pytest.raises(SystemExit) as done:
        languages_run.main(argv)
    assert done.value.code == 2 and named in capsys.readouterr().err


def _passes(folder: Path, *, silero_end: float) -> list[str]:
    """Two off passes and a Silero pass of one variant, as folders."""
    made = []
    for name, classifier, end in (
        ("off1", "off", 2500.0),
        ("silero", "silero", silero_end),
        ("off2", "off", 2520.0),
    ):
        by = "session" if classifier == "off" else "short"
        results = (result("i1", turn(by, end_ms=end)),)
        made.append(str(pass_folder(folder / name, run_info(name, classifier=classifier), results)))
    return made


def test_read_logs_condition_4_for_each_classifier_pass(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert languages_run.main(["--read", *_passes(tmp_path / "near", silero_end=2530.0)]) == 0
    logged = capsys.readouterr().out
    assert "condition_4" in logged and "holds=True" in logged and "run=silero" in logged
    assert languages_run.main(["--read", *_passes(tmp_path / "slow", silero_end=2700.0)]) == 0
    assert "holds=False" in capsys.readouterr().out


def test_read_refuses_what_is_no_pass_and_passes_that_do_not_go_together(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    (tmp_path / "empty").mkdir()
    made = _passes(tmp_path / "passes", silero_end=2530.0)
    assert languages_run.main(["--read", str(tmp_path / "empty"), *made]) == 2
    assert "is not a readable scorecard" in capsys.readouterr().out
    assert languages_run.main(["--read", *made[:2]]) == 2
    assert "two off passes" in capsys.readouterr().out


def test_the_peak_memory_is_a_size_or_none() -> None:
    found = languages_setup.peak_mb()
    assert found is None or found > 0
