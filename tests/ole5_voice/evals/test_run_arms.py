"""Run W's arms as `poe eval` options (plan 006's registration, W; run_arms.py): W1 sends the
Whisper prompt the agent would ship, the library's `whisper_prompt` of the declared vocabulary of
the agent `--prompt-agent` names (Ole5's `talker_agent`, Q17), never one from `evals/terms.toml`,
which term recall is scored on; W0 sends none; X sends every variant as Arabic, as an Arabic call
does. Each is recorded in the run's settings, so `eval-compare` names it."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import pytest
from ole5_voice.agent import NO_SEARCH_VERSION, VOCABULARY
from ole5_voice.evals import run
from ole5_voice.evals.items import EVALS, TERMS_FILE, load_terms
from ole5_voice.evals.models import Item
from t2_agentic_voice.languages import whisper_prompt

from tests.ole5_voice.evals.fakes import FakeSpeechToText
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
