"""A `groq` run pins its arm on the command line (evaluation.md, "Running"; plan 002's arms): its
model and timeout are named, and its base URL is `--base-url` or the SDK's own, so no `T2V_`
variable in the shell or the env file changes a registered run. And a run's note never holds an
install placeholder, which would fail the docs check on the committed history for good."""

from __future__ import annotations

from pathlib import Path

import pytest
from ole5_voice.evals import run, run_settings
from t2_agentic_voice import VoiceSettings
from t2_agentic_voice.ports import SpeechToText

from tests.ole5_voice.evals.run_support import DEV, Setup

SHELL = {
    "T2V_STT__TIMEOUT_S": "30",
    "T2V_STT__MODEL": "whisper-large-v3-turbo",
    "T2V_GROQ__BASE_URL": "https://elsewhere.example",
    "T2V_GROQ__API_KEY": "gsk_made-up-key-0000",
}


def _capturing(setup: Setup) -> list[VoiceSettings]:
    built: list[VoiceSettings] = []

    def adapter(settings: VoiceSettings) -> SpeechToText:
        built.append(settings)
        return setup.stt

    setup.adapter = adapter
    return built


def test_the_shell_cannot_change_a_groq_runs_model_timeout_or_address(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    for name, value in SHELL.items():
        monkeypatch.setenv(name, value)
    setup = Setup(tmp_path)
    built = _capturing(setup)
    assert setup.main() == 0  # --model whisper-large-v3 --timeout-s 6, and no --base-url
    [settings] = built
    assert (settings.stt.model, settings.stt.timeout_s) == ("whisper-large-v3", 6.0)
    assert settings.groq.base_url == "https://api.groq.com"
    ((info, _, _, _),) = setup.writer.calls
    shown = {name: info.settings[name] for name in ("stt.model", "stt.timeout_s", "groq.base_url")}
    assert shown == {
        "stt.model": "whisper-large-v3",
        "stt.timeout_s": "6.0",
        "groq.base_url": "https://api.groq.com",
    }
    assert info.model == "whisper-large-v3"


def test_a_base_url_is_taken_from_its_flag_alone(tmp_path: Path) -> None:
    setup = Setup(tmp_path)
    built = _capturing(setup)
    assert setup.main("--base-url", "https://made-up.example", "--env-file", _env(tmp_path)) == 0
    assert built[0].groq.base_url == "https://made-up.example"


def _env(tmp_path: Path) -> str:
    env = tmp_path / "made-up.env"
    env.write_text("T2V_GROQ__API_KEY=gsk_made-up-key-0000\n", encoding="utf-8")
    return str(env)


def test_a_base_url_that_is_not_https_is_refused_without_its_value(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    setup = Setup(tmp_path)
    for url in ("http://api.groq.com", "https://made-up:hunter2@api.groq.com"):
        assert setup.main("--base-url", url) == 2
        out = capsys.readouterr().out
        assert "--base-url is not an https:// URL" in out and "hunter2" not in out
    assert not setup.out().exists()


@pytest.mark.parametrize(
    ("dropped", "message"),
    [(("--model",), "--model"), (("--timeout-s",), "--timeout-s"), ((), "")],
)
def test_a_groq_run_names_its_model_and_its_timeout(
    dropped: tuple[str, ...], message: str, capsys: pytest.CaptureFixture[str]
) -> None:
    argv = ["--answerer", "groq", *DEV[2:], "--price-per-hour", "0.04", "--cap-usd", "1"]
    pinned = {"--model": "whisper-large-v3-turbo", "--timeout-s": "6"}
    argv += [
        part for flag, value in pinned.items() if flag not in dropped for part in (flag, value)
    ]
    if not dropped:
        argv += ["--timeout-s", "0"]
        message = "must be a finite number of seconds above 0"
    with pytest.raises(SystemExit) as done:
        run.main(argv)
    assert done.value.code == 2 and message in capsys.readouterr().err


def test_a_note_holding_an_install_placeholder_is_refused_before_anything_is_sent(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    setup = Setup(tmp_path)
    placeholder = "{{" + "NAME" + "}}"  # written apart, or the docs check flags this file
    with pytest.raises(SystemExit) as done:
        setup.main("--note", f"see {placeholder}")
    assert done.value.code == 2 and "install placeholder" in capsys.readouterr().err
    assert not setup.out().exists()


def test_a_setting_holding_an_install_placeholder_is_refused_before_anything_is_sent(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The settings go into the committed history too: from a flag, or from the env file."""
    placeholder = "{{" + "NAME" + "}}"  # written apart, or the docs check flags this file
    placed = tmp_path / "placed.env"
    placed.write_text(
        f"T2V_GROQ__API_KEY=gsk_made-up-key-0000\nT2V_TRACING__PROJECT=ole5-{placeholder}\n",
        encoding="utf-8",
    )
    url = f"https://made-up.example/{placeholder}"
    for argv, setting in [
        (["--base-url", url, "--env-file", _env(tmp_path)], "groq.base_url"),
        (["--env-file", str(placed)], "tracing.project"),
    ]:
        setup = Setup(tmp_path / setting)
        built = _capturing(setup)
        assert setup.main(*argv) == 2
        out = capsys.readouterr().out
        assert f"{setting} holds an install placeholder" in out
        assert built == [] and not setup.out().exists()


def test_with_no_env_file_named_a_run_reads_the_working_folders(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The library reads no `.env` it is not given (the design's 7.2): the app gives it the
    working folder's, as the golden set's first runs read it (tests/conftest.py switches this
    off for every other test)."""
    monkeypatch.setattr(run_settings, "DOTENV", Path(".env"))
    folder = tmp_path / "working"
    folder.mkdir()
    monkeypatch.chdir(folder)
    keys = []
    for name in ("before", "after"):
        setup = Setup(tmp_path / name)
        built = _capturing(setup)
        assert setup.main() == 0
        keys.append(built[0].groq.resolved_api_key())
        (folder / ".env").write_text("T2V_GROQ__API_KEY=gsk_made-up-key-0000\n", "utf-8")
    assert keys[0] is None and keys[1] is not None


def test_a_run_is_a_developers_whatever_the_environment_names(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A run serves no caller, so its settings run as `env=dev`, recorded so, whatever
    `T2V_ENV` says; and every setting the library has is recorded, a secret as set or not."""
    monkeypatch.setenv("T2V_ENV", "prod")
    monkeypatch.setenv("T2V_SERVER__TURN_SECRET", "made-up-shared-secret-for-tests-01234567")
    setup = Setup(tmp_path)
    built = _capturing(setup)
    assert setup.main("--env-file", _env(tmp_path)) == 0
    assert built[0].env == "dev"
    ((info, _, _, _),) = setup.writer.calls
    assert (info.settings["env"], info.settings["server.turn_secret"]) == ("dev", "set")
    assert (info.settings["join.keys"], info.settings["server.allowed_origins"]) == (
        "not set",
        "0 entries",
    )
    assert info.settings["tts.languages"].startswith('{"ar": {"model": "canopylabs/orpheus')
    assert (info.settings["privacy.consent_version"], info.settings["turns.vad_stop_ms"]) == (
        "none",
        "200",
    )
