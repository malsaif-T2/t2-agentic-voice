"""A pass of one of run H's Scribe arms, `poe eval-languages --scribe-arm` (D-115;
scribe_arm_run.py), with a fake Scribe and no key: each variant's requests shaped as its arm
says, one at a time, the language named, the other languages on the clip and the call
language's prompt; each variant's answers written as it finishes, and the scorecard with the
moves, the error rates, the times, the threshold table, the settings and the spend; `detected`'s
request naming no language sent only for a variant its gate, an offline detected pass, passed,
and a gate that is no detected pass of every variant refused before any clip; the dry estimate
before any clip, `--estimate-only` and the cap; no key; the parser's refusals; and no word heard
in any log."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from ole5_voice.evals import languages_run
from ole5_voice.evals.run_parts import DATA, Choice, Parts, load_plan
from ole5_voice.evals.runs import SCORECARD_FILE
from ole5_voice.evals.scribe_arm_card import ArmScorecard
from ole5_voice.evals.scribe_arms import ARM_TURNS_FILE, ArmResult
from t2_agentic_voice import ProviderError, VoiceSettings
from t2_agentic_voice.ports import SpeechToText, Transcript

from tests.leaks import holding, shown
from tests.ole5_voice.evals.eot_support import Lines, golden_set, parts_of, paused
from tests.ole5_voice.evals.fakes import FakeSpeechToText
from tests.ole5_voice.evals.languages_support import pass_folder, result, run_info, turn
from tests.ole5_voice.evals.run_support import World, make_world

HEARD = "made-up words"  # each variant's reference, heard right


def _heard(language: str, probability: float, text: str = HEARD) -> Transcript:
    return Transcript(
        text=text, language=language, heard_language=language, language_probability=probability
    )


class Made:
    """Stands in for building the adapter: keeps each settings given, hands `stt`."""

    def __init__(self, stt: FakeSpeechToText) -> None:
        self.stt = stt
        self.settings: list[VoiceSettings] = []

    def __call__(self, settings: VoiceSettings) -> SpeechToText:
        self.settings.append(settings)
        return self.stt


def _world(tmp_path: Path) -> tuple[World, Parts]:
    world = make_world(tmp_path)
    found = (paused(world, "p1"), paused(world, "e1", language="english", kind="request"))
    return world, parts_of(world, golden_set(*found))


def _out(world: World) -> Path:
    return world.main / "var" / "runs" / "sa-dev-hinted"


def _argv(world: World, *extra: str, arm: str = "hinted") -> list[str]:
    argv = ["--split", "dev", "--scribe-arm", arm, "--out", str(_out(world))]
    argv += ["--note", "a Scribe arm", "--audio", f"owner={world.audio}"]
    return [*argv, "--price-per-hour", "0.25", "--cap-usd", "1", *extra]


def _main(argv: list[str], parts: Parts, made: Made) -> int:
    return languages_run.main(argv, parts=parts, append_line=Lines(), make_stt=made)


def _gate(
    world: World,
    parts: Parts,
    detects: tuple[str, ...],
    *,
    classifier: str = "detected",
    items: tuple[str, ...] = ("p1", "e1"),
) -> list[str]:
    """`--language-from` an offline pass of the run's data, at its commit: the items `detects`
    long enough that their first turn also goes naming no language."""
    found = tuple(
        result(item, turn("session", detects=item in detects)).model_copy(
            update={"variant": f"{item}-laptop"}
        )
        for item in items
    )
    digest = load_plan(world.top / DATA, Choice(split="dev"), parts).digest
    run = run_info(f"lid1-dev-{classifier}", classifier=classifier, data_digest=digest)
    folder = pass_folder(world.main / "var" / "runs" / run.name, run, found)
    return ["--language-from", str(folder)]


def test_a_hinted_pass_shapes_each_request_and_scores_the_moves(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], caplog: pytest.LogCaptureFixture
) -> None:
    world, parts = _world(tmp_path)
    script: list[Transcript | ProviderError] = [
        _heard("ar", 0.97),  # p1, Saudi, in the Arabic call: stays
        _heard("ar", 0.91),  # p1 in the English call: heard Arabic, moves it (right)
        _heard("en", 0.88),  # e1, English, in the Arabic call: moves it (right)
        ProviderError("timeout", True),  # e1 in the English call: failed
    ]
    made = Made(FakeSpeechToText(script))
    assert _main(_argv(world), parts, made) == 0
    ((settings,),) = [made.settings]
    assert settings.stt.provider == "elevenlabs" and made.stt.closed
    sent = [
        (language, clip.other_languages, prompt is not None)
        for clip, language, prompt in made.stt.calls
    ]
    assert sent == [("ar", ("en",), True), ("en", ("ar",), True)] * 2
    lines = (_out(world) / ARM_TURNS_FILE).read_text(encoding="utf-8").splitlines()
    assert [ArmResult.model_validate_json(line).item for line in lines] == ["p1", "e1"]
    card = ArmScorecard.model_validate_json((_out(world) / SCORECARD_FILE).read_bytes())
    assert card.complete and card.run.arm == "hinted" and card.run.min_probability == 0.8
    moves = card.both.moves
    assert (moves.due, moves.right, moves.missed, moves.wrong) == (2, 2, 0, 0)
    assert (card.both.turns, card.both.failed) == (4, 1)
    assert card.both.errors["saudi"].wer == 0.0 and card.both.errors["english"].turns == 1
    assert card.both.seconds_p50 is not None and len(card.thresholds) == 10
    assert (card.run.requests, card.run.billed_seconds) == (4, 8.0)  # 2 s clips, 4 requests
    assert card.run.cost_usd == pytest.approx(8.0 / 3600 * 0.25)
    recorded = card.run.settings
    assert (recorded["stt.provider"], recorded["stt.model"]) == ("elevenlabs", "scribe_v3")
    assert recorded["run.scribe_arm"] == "hinted" and recorded["elevenlabs.api_key"] == "not set"
    surfaces = shown(caplog=caplog, capsys=capsys)
    assert "requests=4" in surfaces["stdout"]
    assert holding(HEARD, surfaces) == []


def test_the_detected_reference_names_no_language_only_for_a_variant_its_gate_passed(
    tmp_path: Path,
) -> None:
    world, parts = _world(tmp_path)
    gate = _gate(world, parts, ("p1",))
    made = Made(FakeSpeechToText([_heard("ar", 0.9)] * 5))
    assert _main(_argv(world, *gate, arm="detected"), parts, made) == 0
    asked = [(language, prompt is not None) for _, language, prompt in made.stt.calls]
    assert asked == [("ar", True), (None, False), ("en", True), ("ar", True), ("en", True)]
    lines = (_out(world) / ARM_TURNS_FILE).read_text(encoding="utf-8").splitlines()
    assert [ArmResult.model_validate_json(line).detects for line in lines] == [True, False]
    card = ArmScorecard.model_validate_json((_out(world) / SCORECARD_FILE).read_bytes())
    moves = card.both.moves  # p1 moves the English call; e1, ungated, cannot move the Arabic
    assert (moves.due, moves.right, moves.missed, moves.wrong) == (2, 1, 1, 0)
    assert {(r.item, r.detects) for r in card.turns} == {("p1", True), ("e1", False)}
    assert card.run.requests == 5
    assert card.run.settings["run.language_from"] == (
        "lid1-dev-detected (detected), 1 of 2 variants sent naming no language"
    )


def test_the_estimate_alone_builds_no_adapter_and_makes_no_folder(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    world, parts = _world(tmp_path)
    made = Made(FakeSpeechToText())
    gate = _gate(world, parts, ("p1",))
    assert _main(_argv(world, "--estimate-only", *gate, arm="detected"), parts, made) == 0
    assert made.settings == [] and not _out(world).exists()
    logged = capsys.readouterr().out
    for part in ("run_estimate", "arm=detected", "requests=5", "billed_s=10.0"):
        assert part in logged


@pytest.mark.parametrize(
    ("gate", "message"),
    [
        ({"classifier": "silero"}, "is not a detected pass"),
        ({"items": ("p1",)}, "did not feed every variant"),
    ],
    ids=["a classifier's pass", "a pass missing a variant"],
)
def test_a_gate_that_is_no_detected_pass_of_every_variant_is_refused_before_any_clip(
    tmp_path: Path, gate: dict[str, Any], message: str, capsys: pytest.CaptureFixture[str]
) -> None:
    world, parts = _world(tmp_path)
    made = Made(FakeSpeechToText())
    argv = _argv(world, "--estimate-only", *_gate(world, parts, ("p1",), **gate), arm="detected")
    assert _main(argv, parts, made) == 2
    assert made.settings == [] and not _out(world).exists()
    logged = capsys.readouterr().out
    assert message in logged and "run_estimate" not in logged


def test_a_pass_past_the_cap_or_with_no_key_is_refused_before_any_clip(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    world, parts = _world(tmp_path)
    made = Made(FakeSpeechToText())
    argv = [*_argv(world)[:-4], "--price-per-hour", "1000", "--cap-usd", "1"]
    assert _main(argv, parts, made) == 2  # 8 s at $1000 an hour: $2.22
    assert made.settings == [] and not _out(world).exists()
    assert "passes --cap-usd" in capsys.readouterr().out
    found = languages_run.main(_argv(world), parts=parts, append_line=Lines())
    assert found == 2 and not _out(world).exists()
    assert "T2V_ELEVENLABS__API_KEY" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("extra", "message"),
    [
        (
            ["--price-per-hour", "1", "--cap-usd", "1", "--classifier", "silero"],
            "a pass of its own",
        ),
        (["--price-per-hour", "1", "--cap-usd", "1", "--split", "held-out"], "--split dev only"),
        (["--cap-usd", "1"], "a pass needs --price-per-hour"),
        (["--price-per-hour", "1", "--cap-usd", "1", "--scribe-arm", "auto"], "invalid choice"),
        (["--price-per-hour", "1", "--cap-usd", "1", "--scribe-arm", "detected"], "only it"),
        (["--price-per-hour", "1", "--cap-usd", "1", "--language-from", "x"], "only it"),
    ],
)
def test_the_parser_refuses_an_arms_flags_that_do_not_fit(
    extra: list[str], message: str, capsys: pytest.CaptureFixture[str]
) -> None:
    argv = ["--split", "dev", "--scribe-arm", "hinted", "--out", "x", "--note", "n", *extra]
    with pytest.raises(SystemExit) as done:
        languages_run.main(argv)
    assert done.value.code == 2 and message in capsys.readouterr().err


def test_language_from_serves_no_pass_but_the_detected_arms(
    capsys: pytest.CaptureFixture[str],
) -> None:
    argv = ["--split", "dev", "--classifier", "detected", "--out", "x", "--note", "n"]
    with pytest.raises(SystemExit) as done:
        languages_run.main([*argv, "--language-from", "x"])
    assert done.value.code == 2 and "only it" in capsys.readouterr().err
