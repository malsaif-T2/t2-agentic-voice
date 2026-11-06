"""Run W's arms as `poe eval` options (plan 006's registration, W): W1 sends a Whisper prompt built
from a vocabulary file, its terms then the presets' command words of the language sent, trimmed
to Whisper's limit by that order; W0 sends none; X sends every variant as Arabic, as an Arabic
call does. Each is recorded in the run's settings, so `eval-compare` names it."""

from __future__ import annotations

from pathlib import Path

import pytest
from ole5_voice.evals import run, run_settings
from ole5_voice.evals.items import EVALS, TERMS_FILE, load_terms
from ole5_voice.evals.models import Item
from ole5_voice.evals.run_settings import PROMPT_BYTES, whisper_prompts
from t2_agentic_voice import Phrases

from tests.ole5_voice.evals.fakes import FakeSpeechToText
from tests.ole5_voice.evals.run_support import Setup, World


def _vocabulary(tmp_path: Path, *terms: str) -> str:
    path = tmp_path / "terms.toml"
    listed = ", ".join(f'"{term}"' for term in terms)
    path.write_text(f"terms = [{listed}]\n", encoding="utf-8")
    return str(path)


def _sent(setup: Setup) -> list[tuple[str | None, str | None]]:
    """Each request's language and prompt, as the fake speech-to-text got them."""
    stt = setup.stt
    assert isinstance(stt, FakeSpeechToText)
    return [(language, prompt) for _, language, prompt in stt.calls]


def _two_languages(world: World) -> tuple[Item, Item]:
    return (world.item("a", language="english"), world.item("b", "افتح البريد", language="saudi"))


def test_a_prompt_holds_the_terms_then_the_command_words_of_its_language() -> None:
    phrases = Phrases().extend(stop={"ar": ["قف"], "en": ["halt"]}, repeat={"en": ["again"]})
    prompts = whisper_prompts(("Outlook", "PDF"), phrases)
    assert prompts["en"] == run_settings.Prompt("Outlook, PDF, halt, again", 4, 4)
    assert prompts["ar"] == run_settings.Prompt("Outlook, PDF, قف", 3, 3)


def test_a_prompt_is_trimmed_by_its_order_within_whispers_limit() -> None:
    """The first term that does not fit and every one after it are left out, so the order of
    the file is the order of what is kept; a term twice is kept once."""
    terms = [f"term{n:03}" for n in range(60)]
    prompts = whisper_prompts([*terms, "term000"], Phrases())
    kept = prompts["en"].text.split(", ")
    assert kept == terms[: len(kept)] and prompts["en"].of == 60
    assert len(prompts["en"].text.encode("utf-8")) <= PROMPT_BYTES
    assert len(", ".join(terms[: len(kept) + 1]).encode("utf-8")) > PROMPT_BYTES
    arabic = whisper_prompts(["ب" * 100, "a"], Phrases())["ar"]  # 200 bytes, then 3 more
    assert (arabic.kept, arabic.of) == (2, 2)
    assert whisper_prompts(["ب" * 112], Phrases())["ar"].kept == 1  # 224 bytes: it fits
    assert whisper_prompts(["ب" * 113], Phrases())["ar"].text == ""  # 226 bytes: none


def test_the_committed_vocabulary_keeps_every_product_term_first() -> None:
    terms = load_terms(EVALS / TERMS_FILE)
    for prompt in whisper_prompts(terms).values():
        assert prompt.text.split(", ")[: len(terms)] == list(terms)
        assert prompt.kept > len(terms) and len(prompt.text.encode("utf-8")) <= PROMPT_BYTES


def test_arm_w1_sends_each_language_its_prompt_and_records_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    setup = Setup(tmp_path, _two_languages)
    vocabulary = _vocabulary(tmp_path, "Outlook", "Ole5")
    assert setup.main("--prompt-vocabulary", vocabulary) == 0
    expected = whisper_prompts(("Outlook", "Ole5"))
    sent = _sent(setup)  # the smoke test's first, then each variant
    assert sent[0] == ("en", expected["en"].text)
    assert set(sent[1:]) == {("en", expected["en"].text), ("ar", expected["ar"].text)}
    ((info, _, _, _),) = setup.writer.calls
    recorded = info.settings["run.prompt"]
    english = expected["en"]
    assert recorded.startswith("terms.toml, sha256 ")
    assert f"en {english.kept} of {english.of} terms" in recorded
    out = capsys.readouterr().out
    assert "whisper_prompt" in out and "terms_kept" in out
    assert expected["en"].text not in out  # the counts are logged, not the prompt


def test_arm_w0_sends_no_prompt_and_records_none(tmp_path: Path) -> None:
    setup = Setup(tmp_path, _two_languages)
    assert setup.main() == 0
    assert {prompt for _, prompt in _sent(setup)} == {None}
    ((info, _, _, _),) = setup.writer.calls
    assert (info.settings["run.prompt"], info.settings["run.language_hint"]) == ("none", "label")


def test_arm_x_sends_an_english_item_as_arabic(tmp_path: Path) -> None:
    setup = Setup(tmp_path, _two_languages)
    vocabulary = _vocabulary(tmp_path, "Outlook")
    assert setup.main("--language-hint", "ar", "--prompt-vocabulary", vocabulary) == 0
    arabic = whisper_prompts(("Outlook",))["ar"].text
    assert set(_sent(setup)) == {("ar", arabic)}
    ((info, results, _, _),) = setup.writer.calls
    assert info.settings["run.language_hint"] == "ar"
    assert {r.language for r in results} == {"english", "saudi"}  # the items keep their labels


def test_a_vocabulary_that_does_not_load_is_refused_before_anything_is_sent(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    broken = tmp_path / "broken.toml"
    for text in ('terms = ["PDF", "PDF"]\n', "terms = [\n", 'words = ["PDF"]\n'):
        setup = Setup(tmp_path / str(len(text)))
        broken.write_text(text, encoding="utf-8")
        assert setup.main("--prompt-vocabulary", str(broken)) == 2
        assert "--prompt-vocabulary does not load" in capsys.readouterr().out
        assert setup.calls() == 0 and not setup.out().exists()


def test_a_prompt_needs_a_language_sent(capsys: pytest.CaptureFixture[str]) -> None:
    argv = ["--answerer", "reference", "--split", "dev", "--out", "x", "--note", "n"]
    with pytest.raises(SystemExit) as done:
        run.main([*argv, "--language-hint", "auto", "--prompt-vocabulary", "terms.toml"])
    assert done.value.code == 2 and "not with auto" in capsys.readouterr().err


def test_the_shown_settings_hold_the_prompt(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    setup = Setup(tmp_path)
    vocabulary = _vocabulary(tmp_path, "Outlook")
    argv = ["--show-settings", "--prompt-vocabulary", vocabulary]
    assert run.main(argv, parts=setup.parts()) == 0
    out = capsys.readouterr().out
    assert "run.prompt" in out and "terms.toml, sha256" in out


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
