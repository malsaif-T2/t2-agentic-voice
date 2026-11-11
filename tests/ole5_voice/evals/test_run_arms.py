"""Run W's arms as `poe eval` options (plan 006's registration, W; run_arms.py): W1 sends the
Whisper prompt the agent would ship, the library's `whisper_prompt` of the declared vocabulary of
the agent `--prompt-agent` names (Ole5's `talker_agent`, Q17), never one from `evals/terms.toml`,
which term recall is scored on; W0 sends none; X sends every variant as Arabic, as an Arabic call
does, and C every variant as English, as an English call does. Run H's H2 arm (plan 007's Block
H; language_arms.py), `--language-from` an H1 pass: each variant sent in the language the pass's
rule named for its first turn in the call language `--language-hint` names, with
`--language-base` only the changed ones, the rest the baseline's answers, unsent; the passes and
bases it cannot read refused before anything is sent. Each is recorded in the run's settings, so
`eval-compare` names it."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import pytest
from ole5_voice.agent import NO_SEARCH_VERSION, VOCABULARY
from ole5_voice.evals import run
from ole5_voice.evals.items import EVALS, TERMS_FILE, load_terms
from ole5_voice.evals.models import Item
from ole5_voice.evals.run_parts import DATA, Choice, load_plan
from t2_agentic_voice.languages import whisper_prompt

from tests.ole5_voice.evals.fakes import FakeSpeechToText
from tests.ole5_voice.evals.languages_support import pass_folder, result, run_info, scores, turn
from tests.ole5_voice.evals.run_support import Setup, World

OLE5 = "ole5_voice.agent:talker_agent"
Code = Literal["ar", "en"]
CODES: tuple[Code, ...] = ("ar", "en")


def _prompt(code: Code) -> str:
    return whisper_prompt(VOCABULARY.terms, code).text


def _sent(setup: Setup) -> list[tuple[str | None, str | None]]:
    """Each request's language and prompt, as the fake speech-to-text got them."""
    stt = setup.stt
    assert isinstance(stt, FakeSpeechToText)
    return [(language, prompt) for _, language, prompt in stt.calls]


def _two_languages(world: World) -> tuple[Item, Item]:
    return (world.item("a", language="english"), world.item("b", "افتح البريد", language="saudi"))


def test_ole5s_prompt_keeps_every_declared_term_first_then_its_command_words() -> None:
    for code in CODES:
        prompt = whisper_prompt(VOCABULARY.terms, code)
        assert prompt.text.split(", ")[: len(VOCABULARY.terms)] == list(VOCABULARY.terms)
        assert prompt.kept == prompt.of > len(VOCABULARY.terms)  # every command word fits too


def test_arm_w1_sends_each_language_the_prompt_ole5s_agent_would_ship(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    setup = Setup(tmp_path, _two_languages)
    assert setup.main("--prompt-agent", OLE5) == 0
    sent = _sent(setup)  # the smoke test's first, then each variant
    assert sent[0] == ("en", _prompt("en"))
    assert set(sent[1:]) == {("en", _prompt("en")), ("ar", _prompt("ar"))}
    ((info, _, _, _),) = setup.writer.calls
    recorded = info.settings["run.prompt"]
    english = whisper_prompt(VOCABULARY.terms, "en")
    # Given no knowledge base, the factory gives the talker with no search, versioned apart;
    # its vocabulary, all W1 reads, is the served talker's.
    assert recorded.startswith(f"{OLE5} (ole5 {NO_SEARCH_VERSION}), sha256 ")
    assert f"en {english.kept} of {english.of} words" in recorded
    out = capsys.readouterr().out
    assert "whisper_prompt" in out and "words_kept" in out
    assert _prompt("en") not in out  # the counts are logged, not the prompt


def test_the_prompt_is_never_built_from_the_terms_recall_is_scored_on(tmp_path: Path) -> None:
    """`evals/terms.toml` is the list term recall reads; W1's prompt is the declaration's."""
    scored = load_terms(EVALS / TERMS_FILE)
    assert set(scored) != set(VOCABULARY.terms)  # they differ, so the source shows
    setup = Setup(tmp_path, _two_languages)
    assert setup.main("--prompt-agent", OLE5) == 0
    assert {prompt for _, prompt in _sent(setup)} == {_prompt("en"), _prompt("ar")}


def test_arm_w0_sends_no_prompt_and_records_none(tmp_path: Path) -> None:
    setup = Setup(tmp_path, _two_languages)
    assert setup.main() == 0
    assert {prompt for _, prompt in _sent(setup)} == {None}
    ((info, _, _, _),) = setup.writer.calls
    assert (info.settings["run.prompt"], info.settings["run.language_hint"]) == ("none", "label")


def test_arm_x_sends_an_english_item_as_arabic(tmp_path: Path) -> None:
    setup = Setup(tmp_path, _two_languages)
    assert setup.main("--language-hint", "ar", "--prompt-agent", OLE5) == 0
    assert set(_sent(setup)) == {("ar", _prompt("ar"))}
    ((info, results, _, _),) = setup.writer.calls
    assert info.settings["run.language_hint"] == "ar"
    assert {r.language for r in results} == {"english", "saudi"}  # the items keep their labels


@pytest.mark.parametrize(
    ("named", "says"),
    [
        ("ole5_voice.no_such_module:x", "names no callable"),
        ("os.path:join", "is not a module:name inside ole5_voice"),
        ("ole5_voice.agent:search_tool", "gave no"),  # given no base, it fails as a factory
    ],
)
def test_a_prompt_agent_that_cannot_be_built_is_refused_before_anything_is_sent(
    tmp_path: Path, named: str, says: str, capsys: pytest.CaptureFixture[str]
) -> None:
    setup = Setup(tmp_path)
    assert setup.main("--prompt-agent", named) == 2
    assert says in capsys.readouterr().out
    assert setup.calls() == 0 and not setup.out().exists()


def test_a_prompt_needs_a_language_sent(capsys: pytest.CaptureFixture[str]) -> None:
    argv = ["--answerer", "reference", "--split", "dev", "--out", "x", "--note", "n"]
    with pytest.raises(SystemExit) as done:
        run.main([*argv, "--language-hint", "auto", "--prompt-agent", OLE5])
    assert done.value.code == 2 and "not with auto" in capsys.readouterr().err


def test_the_shown_settings_hold_the_prompt(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    setup = Setup(tmp_path)
    argv = ["--show-settings", "--prompt-agent", OLE5]
    assert run.main(argv, parts=setup.parts()) == 0
    out = capsys.readouterr().out
    assert "run.prompt" in out and f"{OLE5} (ole5 {NO_SEARCH_VERSION}), sha256" in out


def test_a_run_whose_least_cost_passes_the_cap_is_refused_before_anything_is_sent(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Each request is billed at least 10 s: three (the smoke test's and two) cost $0.000925 at
    $0.111 an hour, past a $0.0005 cap; the smoke test's alone, $0.000308, is within it."""
    setup = Setup(tmp_path / "whole", _two_languages)
    assert setup.main("--cap-usd", "0.0005") == 2
    assert "least cost, $0.0009, passes --cap-usd" in capsys.readouterr().out
    assert setup.calls() == 0 and not setup.out().exists()
    smoke = Setup(tmp_path / "smoke", _two_languages)
    assert smoke.main("--cap-usd", "0.0005", "--smoke-only") == 0 and smoke.calls() == 1


def test_arm_c_sends_every_variant_as_english(tmp_path: Path) -> None:
    setup = Setup(tmp_path, _two_languages)
    assert setup.main("--language-hint", "en", "--prompt-agent", OLE5) == 0
    assert set(_sent(setup)) == {("en", _prompt("en"))}
    ((info, _, _, _),) = setup.writer.calls
    assert info.settings["run.language_hint"] == "en" and "run.language_from" not in info.settings


def _digest(setup: Setup) -> str:
    """The digest of the run's data, as `load_plan` gives it for the dev split."""
    return load_plan(setup.world.top / DATA, Choice(split="dev"), setup.parts()).digest


def _h1_pass(setup: Setup, english_in: tuple[str, ...], name: str = "lid1-dev-silero") -> Path:
    """An H1 pass of the dev split, at the run's commit and on its data: the variants of the
    items `english_in` classified English in their first turn, the others Arabic."""
    results = tuple(
        result(item, turn(verdict=scores(0.9 if item in english_in else 0.1)))
        for item in ("a", "b")
    )
    run = run_info(name, data_digest=_digest(setup))
    return pass_folder(setup.world.main / "var" / "runs" / name, run, results)


def test_the_language_arm_sends_each_variant_in_its_first_turns_language(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """In an Arabic call, the English item a heard as English goes as English; b, Arabic,
    heard as English, goes as English too: both changed, both sent, every request with that
    language's prompt."""
    setup = Setup(tmp_path, _two_languages)
    found = _h1_pass(setup, ("a", "b"))
    argv = ["--language-hint", "ar", "--prompt-agent", OLE5, "--language-from", str(found)]
    assert setup.main(*argv) == 0
    assert _sent(setup) == [("en", _prompt("en"))] * 3  # the smoke test's, then a's and b's
    ((info, results, _, _),) = setup.writer.calls
    assert info.settings["run.language_from"] == (
        "lid1-dev-silero (silero), call ar, 2 of 2 variants changed, 0 whose turns differ, "
        "every variant sent"
    )
    assert [r.variant for r in results] == ["a-v1", "b-v1"]
    assert "language_arm" in capsys.readouterr().out


def test_with_a_base_only_the_changed_variants_are_sent(tmp_path: Path) -> None:
    """The ordinary call holds a in English and b in Arabic; the pass heard b as English, so b
    alone is sent, and a's answer is the baseline's, unsent."""
    setup = Setup(tmp_path, _two_languages)
    setup.stt = FakeSpeechToText(["smoke", "open the inbox", "base b", "smoke", "arm b"])
    assert setup.main("--prompt-agent", OLE5, out="base") == 0
    found = _h1_pass(setup, ("a", "b"))
    extra = ["--language-from", str(found), "--language-base", str(setup.out("base"))]
    assert setup.main("--prompt-agent", OLE5, *extra, out="arm") == 0
    sent = _sent(setup)
    assert len(sent) == 5 and sent[3:] == [("en", _prompt("en"))] * 2  # the smoke, then b
    (_, base, _, _), (info, arm, _, _) = setup.writer.calls
    assert arm[0].answer == base[0].answer and arm[1].answer.text == "arm b"
    assert "1 of 2 variants changed" in info.settings["run.language_from"]
    assert "the rest from base" in info.settings["run.language_from"]


@pytest.mark.parametrize(
    ("change", "says"),
    [
        ({"commit": "cd" * 20}, "not at this commit"),
        ({"classifier": "off"}, "classifies nothing"),
        ({"split": "held-out"}, "not of the run's split"),
        ({"data_digest": "0" * 64}, "not on the run's data"),
    ],
)
def test_a_pass_the_arm_cannot_read_is_refused_before_anything_is_sent(
    tmp_path: Path, change: dict[str, str], says: str, capsys: pytest.CaptureFixture[str]
) -> None:
    setup = Setup(tmp_path, _two_languages)
    run = run_info("lid1-dev-silero", data_digest=_digest(setup)).model_copy(update=change)
    side = change.get("split", "dev")
    results = (result("a", turn(), split=side), result("b", turn(), split=side))
    found = pass_folder(setup.world.main / "var" / "runs" / "lid1", run, results)
    assert setup.main("--language-from", str(found)) == 2
    assert says in capsys.readouterr().out
    assert setup.calls() == 0 and not setup.out().exists()


def test_an_incomplete_pass_a_missing_variant_and_a_folder_that_is_no_pass_are_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    setup = Setup(tmp_path, _two_languages)
    run = run_info("lid1-dev-silero", data_digest=_digest(setup))
    runs = setup.world.main / "var" / "runs"
    unfinished = pass_folder(runs / "u", run, (result("a", turn()),), complete=False)
    assert setup.main("--language-from", str(unfinished)) == 2
    assert "not complete" in capsys.readouterr().out
    partial = pass_folder(runs / "p", run, (result("a", turn()),))
    assert setup.main("--language-from", str(partial)) == 2
    assert "did not feed every variant" in capsys.readouterr().out
    (runs / "none").mkdir()
    assert setup.main("--language-from", str(runs / "none")) == 2
    assert "is not a readable scorecard" in capsys.readouterr().out
    assert setup.calls() == 0


def test_a_base_of_another_call_language_or_prompt_is_refused(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    setup = Setup(tmp_path, _two_languages)
    assert setup.main(out="base") == 0  # the ordinary call's baseline, with no prompt
    found = _h1_pass(setup, ("b",))
    extra = ["--language-from", str(found), "--language-base", str(setup.out("base"))]
    sent = setup.calls()
    assert setup.main("--language-hint", "ar", *extra, out="arm") == 2
    assert "not a baseline of this call" in capsys.readouterr().out
    assert setup.main("--prompt-agent", OLE5, *extra, out="arm") == 2
    assert "not a baseline of this call" in capsys.readouterr().out
    assert setup.calls() == sent and not setup.out("arm").exists()


@pytest.mark.parametrize(
    ("extra", "says"),
    [
        (["--language-hint", "auto", "--language-from", "p"], "names the call's language"),
        (["--language-base", "b"], "--language-base serves --language-from"),
        (["--language-from", "p", "--windows-ms", "500"], "sends whole variants"),
        (["--language-from", "p", "--questions", "q"], "sends whole variants"),
    ],
)
def test_the_flags_the_language_arm_needs(
    extra: list[str], says: str, capsys: pytest.CaptureFixture[str]
) -> None:
    argv = ["--answerer", "reference", "--split", "dev", "--out", "x", "--note", "n"]
    with pytest.raises(SystemExit) as done:
        run.main([*argv, *extra])
    assert done.value.code == 2 and says in capsys.readouterr().err


def test_a_held_out_arm_takes_no_base(capsys: pytest.CaptureFixture[str]) -> None:
    argv = ["--answerer", "reference", "--split", "held-out", "--out", "x", "--note", "n"]
    with pytest.raises(SystemExit) as done:
        run.main([*argv, "--language-from", "p", "--language-base", "b"])
    assert done.value.code == 2 and "a held-out arm sends every variant" in capsys.readouterr().err
