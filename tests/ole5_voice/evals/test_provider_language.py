"""A speech-to-text provider's own language as a pass of `poe eval-languages` (D-100;
provider_language.py), with the fake `SpeechToText` and no key: the providers that report a
language, each answer as the scores the rule reads, one classification at a time, each request
billed as it is sent; a provider's pass through a fake `turn_languages` that asks the
classifier, its settings, model and spend recorded on the scorecard and history line; the dry
estimate before any clip, `--estimate-only` and the cap; no key; and no word heard in any
log."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterable
from pathlib import Path
from typing import Any, get_args

import pytest
from ole5_voice.evals import history, languages_run
from ole5_voice.evals.languages_card import ClassifierName, LanguagesLine, LanguagesScorecard
from ole5_voice.evals.provider_language import (
    PROVIDERS,
    ProviderLanguage,
    code_of,
    provider_language,
    scores_of,
)
from ole5_voice.evals.run_parts import Parts
from ole5_voice.evals.runs import SCORECARD_FILE
from ole5_voice.evals.stt_arms import ARMS
from t2_agentic_voice import ConfigurationError, ProviderError, VoiceSettings
from t2_agentic_voice.domain.turn_language import LanguageRule, choose_language
from t2_agentic_voice.evals import LanguageTurn
from t2_agentic_voice.ports import AudioClip, Transcript

from tests.leaks import holding, shown
from tests.ole5_voice.evals.eot_support import Lines, golden_set, parts_of, paused
from tests.ole5_voice.evals.fakes import FakeSpeechToText
from tests.ole5_voice.evals.languages_support import turn
from tests.ole5_voice.evals.run_support import World, make_world

AMONG = ("ar", "en")
HEARD = "the caller's own words"
TWO_S = AudioClip(pcm16=b"\x00\x00" * 32_000)


def _heard(language: str | None, probability: float | None = None) -> Transcript:
    """A provider's answer to a request that named no language."""
    return Transcript(
        text=HEARD, language=None, heard_language=language, language_probability=probability
    )


def test_the_providers_that_report_a_language_are_the_passes_classifiers() -> None:
    assert PROVIDERS == ("groq", "elevenlabs", "soniox")
    assert get_args(ClassifierName) == ("off", "silero", "ecapa", "detected", *PROVIDERS)
    assert not ARMS["speechmatics"].hears_language and not ARMS["cohere"].hears_language


@pytest.mark.parametrize(
    ("heard", "code"),
    [
        ("ar", "ar"),
        ("AR-sa", "ar"),
        ("en_US", "en"),
        ("Arabic", "ar"),
        (" english ", "en"),
        ("armenian", None),
        ("fr", None),
        ("", None),
        (None, None),
    ],
)
def test_a_providers_language_names_a_code_exactly(heard: str | None, code: str | None) -> None:
    assert code_of(heard, AMONG) == code


def test_a_providers_answer_becomes_the_scores_the_rule_reads() -> None:
    scored = scores_of(_heard("en", 0.82), AMONG)
    assert scored.shares == pytest.approx({"ar": 0.18, "en": 0.82}) and scored.mass == 0.82
    whisper = Transcript(text=HEARD, language="Arabic")  # Groq, told no language
    assert scores_of(whisper, AMONG).shares == {"ar": 1.0, "en": 0.0}
    assert scores_of(_heard("en"), AMONG).best == ("en", 1.0)  # Soniox: no score
    for other in (_heard("fr", 0.99), _heard(None)):
        unsure = scores_of(other, AMONG)
        assert (unsure.shares, unsure.mass) == ({"ar": 0.5, "en": 0.5}, 0.0)


@pytest.mark.parametrize("probability", [0.25, 0.3, 0.49])
def test_a_providers_low_score_never_makes_the_language_it_did_not_hear_the_best(
    probability: float,
) -> None:
    unsure = scores_of(_heard("ar", probability), AMONG)
    assert (unsure.shares, unsure.mass) == ({"ar": 0.5, "en": 0.5}, probability)
    rule = LanguageRule(from_s=2.0, min_share=0.7)
    assert choose_language("ar", unsure, speech_s=2.0, rule=rule).by == "unsure"
    assert choose_language("en", unsure, speech_s=2.0, rule=rule).language == "en"
    three = scores_of(_heard("ar", 0.4), ("ar", "en", "fr"))
    assert three.best == ("ar", 0.4) and three.shares["en"] == pytest.approx(0.3)


def test_a_classification_sends_no_language_or_prompt_and_is_billed_as_sent() -> None:
    fake = FakeSpeechToText([_heard("en", 0.9), ProviderError("timeout", True)])
    groq = ProviderLanguage(fake, ARMS["groq"])
    found = asyncio.run(groq.classify(TWO_S, among=AMONG))
    assert found is not None and found.best == ("en", 0.9)
    with pytest.raises(ProviderError):
        asyncio.run(groq.classify(TWO_S, among=AMONG))
    assert [(language, prompt) for _, language, prompt in fake.calls] == [(None, None)] * 2
    assert (groq.requests, groq.billed_seconds) == (2, 20.0)  # Groq's 10 s a request, failed too
    kept = FakeSpeechToText([_heard("ar", 0.7)])
    scribe = ProviderLanguage(kept, ARMS["elevenlabs"])
    asyncio.run(scribe.classify(TWO_S, among=AMONG))
    assert scribe.billed_seconds == 2.0 and scribe.name == "elevenlabs-language"
    asyncio.run(scribe.aclose())
    assert kept.closed


def test_a_second_ask_while_one_is_out_is_answered_busy() -> None:
    fake = FakeSpeechToText([_heard("ar")], delay_s=0.05)
    classifier = ProviderLanguage(fake, ARMS["soniox"])

    async def both() -> list[object]:
        first = asyncio.create_task(classifier.classify(TWO_S, among=AMONG))
        await asyncio.sleep(0)
        second = await classifier.classify(TWO_S, among=AMONG)
        return [await first, second]

    first, second = asyncio.run(both())
    assert first is not None and second is None and classifier.requests == 1


def test_a_provider_with_no_key_is_refused_naming_its_setting() -> None:
    settings = VoiceSettings.model_validate({"env": "test", "stt": {"provider": "elevenlabs"}})
    with pytest.raises(ConfigurationError) as refused:
        provider_language(settings)
    assert "T2V_ELEVENLABS__API_KEY" in refused.value.message


class AskingTurnLanguages:
    """Stands in for `evals.turn_languages`: each clip's first 2 s asked of the classifier once,
    one classified turn a clip, keeping what it was asked."""

    def __init__(self) -> None:
        self.asked: dict[str, Any] = {}

    async def __call__(
        self, clips: Iterable[AudioClip], **asked: Any
    ) -> AsyncIterator[tuple[LanguageTurn, ...]]:
        self.asked = asked
        for clip in clips:
            head = AudioClip(pcm16=clip.pcm16[:64_000])
            await asked["classifier"].classify(head, among=AMONG)
            yield (turn(named="en"),)


class Providers:
    """Stands in for building the provider's classifier: keeps each settings given."""

    def __init__(self, stt: FakeSpeechToText) -> None:
        self.stt = stt
        self.settings: list[VoiceSettings] = []
        self.made: ProviderLanguage | None = None

    def __call__(self, settings: VoiceSettings) -> ProviderLanguage:
        self.settings.append(settings)
        self.made = ProviderLanguage(self.stt, ARMS[settings.stt.provider])
        return self.made


def _world(tmp_path: Path) -> tuple[World, Parts]:
    world = make_world(tmp_path)
    found = (paused(world, "p1"), paused(world, "e1", language="english", kind="request"))
    return world, parts_of(world, golden_set(*found))


def _out(world: World) -> Path:
    return world.main / "var" / "runs" / "lid1-dev-scribe"


def _argv(world: World, *extra: str, classifier: str = "elevenlabs") -> list[str]:
    argv = ["--split", "dev", "--classifier", classifier, "--out", str(_out(world))]
    argv += ["--note", "a provider pass", "--audio", f"owner={world.audio}"]
    return [*argv, "--price-per-hour", "0.4", "--cap-usd", "1", *extra]


def _main(argv: list[str], parts: Parts, made: Providers, lines: Lines | None = None) -> int:
    return languages_run.main(
        argv,
        parts=parts,
        turn_languages=AskingTurnLanguages(),
        make_provider=made,
        append_line=lines or Lines(),
        peak=lambda: None,
    )


def test_a_providers_pass_hears_each_turn_through_it_and_records_what_it_spent(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], caplog: pytest.LogCaptureFixture
) -> None:
    world, parts = _world(tmp_path)
    made, lines = Providers(FakeSpeechToText([_heard("en", 0.9)] * 2)), Lines()
    assert _main(_argv(world), parts, made, lines) == 0
    ((settings,),) = [made.settings]
    assert (settings.stt.provider, settings.stt.live_language) == ("elevenlabs", "classified")
    assert made.made is not None and made.made.requests == 2 and made.stt.closed
    card = LanguagesScorecard.model_validate_json((_out(world) / SCORECARD_FILE).read_bytes())
    run = card.run
    assert (run.classifier, run.price_per_hour_usd, run.billed_seconds) == ("elevenlabs", 0.4, 4.0)
    assert run.cost_usd == pytest.approx(4.0 / 3600 * 0.4)
    recorded = run.settings
    assert (recorded["stt.provider"], recorded["stt.model"]) == ("elevenlabs", "scribe_v3")
    assert recorded["elevenlabs.api_key"] == "not set" and recorded["stt.classifier"] == "none"
    assert recorded["run.price_per_hour"] == "0.4"
    (line, _), _ = lines.appended
    assert isinstance(line, LanguagesLine) and line.cost_usd == run.cost_usd
    page = history.render_history([line])
    assert "Price per hour of audio | $0.4" in page and f"${run.cost_usd:.4f}" in page
    surfaces = shown(caplog=caplog, capsys=capsys)
    assert "most_requests=6" in surfaces["stdout"]  # 2 s clips with 4.5 s after: 3 each
    assert holding(HEARD, surfaces) == []


def test_the_estimate_alone_builds_no_provider_and_makes_no_folder(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    world, parts = _world(tmp_path)
    made = Providers(FakeSpeechToText())
    assert _main(_argv(world, "--estimate-only", classifier="groq"), parts, made) == 0
    assert made.settings == [] and not _out(world).exists()
    logged = capsys.readouterr().out
    for part in ("run_estimate", "provider=groq", "most_requests=6", "most_billed_s=60.0"):
        assert part in logged


def test_a_pass_whose_most_cost_passes_the_cap_is_refused_before_any_clip(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    world, parts = _world(tmp_path)
    made = Providers(FakeSpeechToText())
    argv = [*_argv(world, classifier="groq")[:-4], "--price-per-hour", "100", "--cap-usd", "1"]
    assert _main(argv, parts, made) == 2  # 60 s at $100 an hour: $1.67
    assert made.settings == [] and not _out(world).exists()
    assert "passes --cap-usd" in capsys.readouterr().out


def test_a_providers_pass_with_no_key_is_refused_before_any_clip(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    world, parts = _world(tmp_path)
    found = languages_run.main(_argv(world), parts=parts, append_line=Lines())
    assert found == 2 and not _out(world).exists()
    assert "T2V_ELEVENLABS__API_KEY" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("classifier", "extra", "message"),
    [
        ("soniox", ["--cap-usd", "1"], "a pass needs --price-per-hour"),
        ("silero", ["--cap-usd", "1"], "serve a provider's pass"),
        ("off", ["--estimate-only"], "serve a provider's pass"),
        ("speechmatics", ["--price-per-hour", "1", "--cap-usd", "1"], "invalid choice"),
    ],
)
def test_the_parser_refuses_a_providers_flags_that_do_not_fit(
    classifier: str, extra: list[str], message: str, capsys: pytest.CaptureFixture[str]
) -> None:
    argv = ["--split", "dev", "--classifier", classifier, "--out", "x", "--note", "n", *extra]
    with pytest.raises(SystemExit) as done:
        languages_run.main(argv)
    assert done.value.code == 2 and message in capsys.readouterr().err
