"""`poe eval`'s speech-to-text providers (D-100), with the fake `SpeechToText` and no key: each
provider the library's `stt.provider` takes is an answerer, its settings and model pinned on
the scorecard and the history line, billed as it bills; the dry estimate logged before anything
is sent, `--estimate-only` stopping there; and what the parser refuses of a provider's flags."""

from __future__ import annotations

from pathlib import Path
from typing import get_args

import pytest
from ole5_voice.evals import run
from ole5_voice.evals.answerers import ANSWERERS
from ole5_voice.evals.stt_arms import ARMS, recorded_model
from t2_agentic_voice import VoiceSettings
from t2_agentic_voice.adapters import (
    cohere_stt,
    elevenlabs_stt,
    nabrah_stt,
    soniox_stt,
    speechmatics_stt,
    telnyx_stt,
)
from t2_agentic_voice.core.settings.stt import WHISPER_MIN_BILLED_S, SttProvider
from t2_agentic_voice.ports import SpeechToText

from tests.ole5_voice.evals.fakes import FakeSpeechToText
from tests.ole5_voice.evals.run_support import Setup

HEARD = ["open the inbox"] * 4


def test_every_provider_the_library_takes_is_an_answerer_with_its_adapters_model() -> None:
    assert tuple(ARMS) == get_args(SttProvider) and ("reference", *ARMS) == ANSWERERS
    models = {name: arm.model for name, arm in ARMS.items()}
    assert models == {
        "groq": None,
        "elevenlabs": elevenlabs_stt.MODEL,
        "speechmatics": f"{speechmatics_stt.LANGUAGE_PACK}-enhanced",
        "cohere": cohere_stt.MODEL,
        "soniox": soniox_stt.MODEL,
        "telnyx": None,
        "nabrah": nabrah_stt.MODEL,
    }
    assert ARMS["groq"].minimum_s == WHISPER_MIN_BILLED_S
    assert [name for name, arm in ARMS.items() if arm.names_language] == ["cohere"]
    settings = VoiceSettings.model_validate({"env": "test"})
    assert recorded_model(settings, "groq") == "whisper-large-v3"
    assert recorded_model(settings, "soniox") == "stt-async-v6"
    assert recorded_model(settings, "telnyx") == telnyx_stt.MODEL == "humain/realtime"
    nova = VoiceSettings.model_validate({"env": "test", "telnyx": {"stt_model": "deepgram/nova-3"}})
    assert recorded_model(nova, "telnyx") == "deepgram/nova-3"


def _provider_setup(tmp_path: Path) -> tuple[Setup, list[str]]:
    """A run's world whose adapter records the provider the settings name."""
    setup = Setup(tmp_path)
    setup.stt = FakeSpeechToText(HEARD)
    named: list[str] = []

    def adapter(settings: VoiceSettings) -> SpeechToText:
        named.append(settings.stt.provider)
        return setup.stt

    setup.adapter = adapter
    return setup, named


def test_a_providers_run_names_it_records_its_model_and_bills_the_audio_sent(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    setup, named = _provider_setup(tmp_path)
    assert setup.main(answerer="elevenlabs") == 0
    assert named == ["elevenlabs"] and setup.calls() == 4
    ((info, _, _, _),) = setup.writer.calls
    assert (info.answerer, info.model, info.settings["stt.provider"]) == (
        "elevenlabs",
        "scribe_v3",
        "elevenlabs",
    )
    assert info.settings["elevenlabs.api_key"] == "not set"
    line, _ = setup.history.lines
    assert (line.answerer, line.model) == ("elevenlabs", "scribe_v3")
    assert 0 < line.billed_seconds < 4 * WHISPER_MIN_BILLED_S  # no 10 s minimum a request
    out = capsys.readouterr().out
    assert "run_estimate" in out and "provider=elevenlabs" in out and "requests=4" in out


def test_no_t2v_variable_changes_the_provider_a_run_names(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("T2V_STT__PROVIDER", "speechmatics")
    setup, named = _provider_setup(tmp_path)
    assert setup.main(answerer="soniox") == 0
    assert named == ["soniox"]


def test_the_dry_estimate_alone_sends_nothing_builds_no_adapter_and_needs_no_key(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    setup, named = _provider_setup(tmp_path)
    assert setup.main("--estimate-only", "--max-rpm", "5", answerer="cohere") == 0
    assert (named, setup.calls(), setup.writer.calls, setup.history.lines) == ([], 0, [], [])
    assert not setup.out().exists()
    out = capsys.readouterr().out
    for shown in ("run_estimate", "provider=cohere", "requests=4", "least_minutes=0.8"):
        assert shown in out
    assert "open the inbox" not in out


def test_a_groq_estimate_counts_its_ten_second_minimum_and_the_cap_still_refuses(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    setup, _ = _provider_setup(tmp_path)
    assert setup.main("--estimate-only") == 0
    assert "least_billed_s=40.0" in capsys.readouterr().out
    assert setup.main("--price-per-hour", "3600", out="r2") == 2  # $40 at the least, cap $1
    assert setup.calls() == 0


@pytest.mark.parametrize(
    ("extra", "message"),
    [
        (["--answerer", "elevenlabs", "--model", "whisper-large-v3"], "are Groq's"),
        (["--answerer", "soniox", "--base-url", "https://api.groq.com"], "are Groq's"),
        (["--answerer", "cohere", "--max-rpm", "5", "--language-hint", "auto"], "detects no"),
        (["--answerer", "cohere"], "allows --max-rpm 5 at the most"),
        (["--answerer", "reference", "--estimate-only"], "--estimate-only serves"),
        (["--answerer", "groq", "--estimate-only", "--windows-ms", "500"], "no --windows-ms"),
    ],
)
def test_the_parser_refuses_a_providers_flags_that_do_not_fit_it(
    extra: list[str], message: str, capsys: pytest.CaptureFixture[str]
) -> None:
    argv = ["--split", "dev", "--out", "x", "--note", "n", "--price-per-hour", "1"]
    argv += ["--cap-usd", "1", "--timeout-s", "6", *extra]
    argv += ["--model", "whisper-large-v3"] if "groq" in extra else []
    with pytest.raises(SystemExit) as done:
        run.main(argv)
    assert done.value.code == 2 and message in capsys.readouterr().err


def test_a_provider_run_needs_its_price_cap_and_timeout_but_no_model(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit):
        run.main(["--answerer", "speechmatics", "--split", "dev", "--out", "x", "--note", "n"])
    error = capsys.readouterr().err.splitlines()[-1]
    assert error == "poe eval: error: a run needs --timeout-s, --price-per-hour, --cap-usd"
