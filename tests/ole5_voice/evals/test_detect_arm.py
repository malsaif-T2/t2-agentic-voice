"""Run H's Whisper arm of `stt.live_language = "detected"` (D-038's amendment; detect_arm.py,
language_arms.py) as `poe eval --language-from <a detected pass> --language-base <base>`: only
the variants whose first turn detects are sent, naming no language and with no prompt; each
answer read with the library's rule against the baseline's, the detecting request's words kept
only when the call would move, never for a short reply or a third language; each detecting
request's time logged beside the baseline's, moved or not, never its words; a detected pass with
no base refused before anything is sent."""

from __future__ import annotations

from pathlib import Path

import pytest
from ole5_voice.evals.models import Item
from ole5_voice.evals.runs import Answer
from t2_agentic_voice.ports import Transcript

from tests.ole5_voice.evals.fakes import FakeSpeechToText
from tests.ole5_voice.evals.languages_support import pass_folder, result, run_info, turn
from tests.ole5_voice.evals.run_support import Setup, World
from tests.ole5_voice.evals.test_run_arms import OLE5, _digest, _prompt, _sent

# What Whisper writes for the English item told Arabic: Arabic sounds (plan 006's run X).
SOUNDS = "اوبن ذا انبوكس"


def _items(world: World) -> tuple[Item, Item]:
    return (world.item("a", language="english"), world.item("b", "افتح البريد", language="saudi"))


def _detected_pass(setup: Setup, detects: tuple[str, ...], *, split: str = "dev") -> Path:
    """A detected pass of the run's data, at its commit: the items `detects` long enough that
    their first turn also goes naming no language."""
    found = tuple(
        result(item, turn("session", detects=item in detects), split=split) for item in ("a", "b")
    )
    run = run_info("lid1-dev-detected", classifier="detected", split=split)
    run = run.model_copy(update={"data_digest": _digest(setup)})
    return pass_folder(setup.world.main / "var" / "runs" / run.name, run, found)


def _detected(text: str, language: str = "english") -> Transcript:
    return Transcript(text=text, language=language, billed_seconds=10.0)


def _arm(tmp_path: Path, heard: Transcript) -> tuple[Setup, tuple[Answer, Answer], str]:
    """A base of the Arabic call, then the arm with a detecting, b not: the arm's answers and
    what the run recorded of it."""
    setup = Setup(tmp_path, _items)
    setup.stt = FakeSpeechToText(["smoke", SOUNDS, "افتح البريد", "smoke", heard])
    hint = ["--language-hint", "ar", "--prompt-agent", OLE5]
    assert setup.main(*hint, out="base") == 0
    found = _detected_pass(setup, ("a",))
    extra = ["--language-from", str(found), "--language-base", str(setup.out("base"))]
    assert setup.main(*hint, *extra, out="arm") == 0
    (_, base, _, _), (info, arm, _, _) = setup.writer.calls
    assert arm[1].answer == base[1].answer  # b did not detect: the baseline's, unsent
    assert _sent(setup)[3:] == [("en", _prompt("en")), (None, None)]  # the smoke, then a
    return setup, (base[0].answer, arm[0].answer), info.settings["run.language_from"]


def test_an_english_question_heard_by_detection_is_the_arms_answer_and_moves_the_call(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _, (base, arm), recorded = _arm(tmp_path, _detected("open the inbox"))
    assert (arm.text, arm.language) == ("open the inbox", "en")
    assert base.text == SOUNDS
    assert recorded == (
        "lid1-dev-detected (detected), call ar, 1 of 2 variants sent naming no language, "
        "the rest from base"
    )
    logged = capsys.readouterr().out
    assert "language_moved" in logged and "open the inbox" not in logged


@pytest.mark.parametrize(
    "heard",
    [_detected("okay thanks"), _detected("ouvrez la boite", "french"), _detected("inbox")],
    ids=["a short reply", "a third language", "one word"],
)
def test_a_detection_the_rule_refuses_keeps_the_baselines_answer(
    tmp_path: Path, heard: Transcript, capsys: pytest.CaptureFixture[str]
) -> None:
    _, (base, arm), _ = _arm(tmp_path, heard)
    assert arm == base
    logged = [line for line in capsys.readouterr().out.splitlines() if "detect_answered" in line]
    assert len(logged) == 1 and "latency_ms=" in logged[0] and "base_ms=" in logged[0]
    assert "variant=a" in logged[0] and heard.text not in logged[0]


def test_a_detected_pass_needs_the_call_languages_base(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    setup = Setup(tmp_path, _items)
    found = _detected_pass(setup, ("a",))
    hint = ["--language-hint", "ar", "--prompt-agent", OLE5, "--language-from", str(found)]
    assert setup.main(*hint) == 2
    assert "against the call language's baseline" in capsys.readouterr().out
    assert setup.calls() == 0
