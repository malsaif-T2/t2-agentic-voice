"""The `t2v` command (api/cli.py): `--help` for it and each command only prints help, importing no
Pipecat and no FastAPI, as `import t2_agentic_voice` imports neither (GP-17), checked in a
child process; `settings show --redacted` shows no secret and no secret's file; `serve` and `dev`
serve the runtime APP names, with logging configured from its settings; and every refusal names
what to fix, never a value. `t2v doctor`: test_doctor.py."""

from __future__ import annotations

import json
import logging
import runpy
import subprocess
import sys
from importlib import metadata
from pathlib import Path

import pytest
import uvicorn
from t2_agentic_voice.api import server
from t2_agentic_voice.api.cli import REDACTED, main

from tests.isolation import child_shell

ROOT = Path(__file__).resolve().parents[3]
KEY = "gsk_made-up-key-0123456789abcdefghijklmnop"
APP = "minimal_example.app:make_runtime"
HELPS = [
    ["--help"],
    ["serve", "--help"],
    ["dev", "--help"],
    ["doctor", "--help"],
    ["settings", "--help"],
    ["settings", "show", "--help"],
]
# The child: import the library, then print each command's help, and say what was imported.
_CHILD = f"""
import contextlib, io, json, sys
HEAVY = ("fastapi", "pipecat", "onnxruntime", "groq", "uvicorn")
import t2_agentic_voice
found = {{"import": sorted(m for m in HEAVY if m in sys.modules), "helps": []}}
from t2_agentic_voice.api.cli import main
for argv in {HELPS!r}:
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        try:
            main(argv)
        except SystemExit as stopped:
            found["helps"].append([stopped.code, out.getvalue()])
found["help"] = sorted(m for m in HEAVY if m in sys.modules)
print(json.dumps(found))
"""


def test_help_only_prints_help_and_imports_nothing_heavy() -> None:
    done = subprocess.run(
        [sys.executable, "-c", _CHILD],
        cwd=ROOT,
        env=child_shell(),
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
        timeout=120,
    )
    assert done.stderr == ""
    found = json.loads(done.stdout)
    assert found["import"] == [] and found["help"] == []
    assert len(found["helps"]) == len(HELPS)
    for code, text in found["helps"]:
        assert code == 0 and text.startswith("usage: t2v")


def test_t2v_is_the_librarys_command() -> None:
    [script] = metadata.entry_points(group="console_scripts", name="t2v")
    assert script.value == "t2_agentic_voice.api.cli:main"


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """`T2V_ENV=dev` and a made-up key set; the settings' folder, the session's scratch one."""
    monkeypatch.setenv("T2V_ENV", "dev")
    monkeypatch.setenv("T2V_GROQ__API_KEY", KEY)
    monkeypatch.setattr(sys, "path", list(sys.path))
    return tmp_path


def test_settings_show_redacts_every_secret_and_its_file(
    env: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    keys = env / "keys.json"
    monkeypatch.setenv("T2V_JOIN__KEYS_FILE", str(keys))
    assert main(["settings", "show", "--redacted"]) == 0
    out = capsys.readouterr().out
    shown = json.loads(out)
    assert shown["groq"]["api_key"] == REDACTED and shown["join"]["keys_file"] == REDACTED
    assert shown["groq"]["api_key_file"] is None and shown["env"] == "dev"
    assert KEY not in out and str(keys) not in out


def test_settings_load_from_the_env_file_given_under_the_prefix_given(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    dotenv = tmp_path / "app.env"
    dotenv.write_text("HELPDESK_VOICE_ENV=staging\n", encoding="utf-8")
    argv = ["settings", "show", "--prefix", "HELPDESK_VOICE_", "--env-file", str(dotenv)]
    assert main(argv) == 0
    assert json.loads(capsys.readouterr().out)["env"] == "staging"


def test_settings_that_cannot_load_are_refused_naming_the_setting(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("T2V_ENV", "zx-made-up-env")
    assert main(["settings", "show"]) == 1
    shown = capsys.readouterr()
    assert shown.out == "" and "T2V_ENV" in shown.err and "FIX:" in shown.err
    assert "zx-made-up-env" not in shown.err


@pytest.fixture
def ran(monkeypatch: pytest.MonkeyPatch) -> list[uvicorn.Config]:
    """Each uvicorn config `t2v` runs, in place of running it."""
    configs: list[uvicorn.Config] = []
    monkeypatch.setattr(server, "run", configs.append)
    return configs


@pytest.mark.parametrize(
    ("argv", "host"),
    [
        (["serve", APP, "--host", "127.0.0.2", "--port", "9003"], "127.0.0.2"),
        (["dev", APP, "--port", "9003"], "127.0.0.1"),
    ],
)
def test_serve_and_dev_serve_the_runtime_app_names(
    argv: list[str], host: str, env: Path, ran: list[uvicorn.Config]
) -> None:
    assert main(argv) == 0
    [config] = ran
    assert (config.host, config.port) == (host, 9003)
    for name in ("t2_agentic_voice", "minimal_example", "__main__", "uvicorn"):
        assert logging.getLogger(name).handlers, name


@pytest.mark.parametrize(
    ("app", "why"),
    [
        ("minimal_example", "is not module:function"),
        ("minimal_example.app:", "is not module:function"),
        ("no_such_module_zx:make", "names no function that can be imported"),
        ("minimal_example.app:missing", "names no function that can be imported"),
        ("minimal_example:LOGGERS", "names no function"),
        ("builtins:dict", "returned no VoiceRuntime"),
    ],
)
def test_an_app_that_names_no_runtime_factory_is_refused(
    app: str, why: str, env: Path, ran: list[uvicorn.Config], capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["serve", app]) == 1
    err = capsys.readouterr().err
    assert why in err and "FIX:" in err and ran == []


def test_apps_are_imported_from_the_working_folder_too(
    env: Path, monkeypatch: pytest.MonkeyPatch, ran: list[uvicorn.Config]
) -> None:
    folder = env / "team"
    folder.mkdir()
    (folder / "zx_team_voice.py").write_text(
        "from minimal_example.app import make_runtime\n", encoding="utf-8"
    )
    monkeypatch.chdir(folder)
    monkeypatch.setattr(sys, "path", [p for p in sys.path if p not in ("", str(folder))])
    monkeypatch.delitem(sys.modules, "zx_team_voice", raising=False)
    assert main(["serve", "zx_team_voice:make_runtime"]) == 0
    assert sys.path[0] == str(folder) and len(ran) == 1


def test_the_module_runs_as_t2v(env: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "argv", ["t2v", "settings", "show"])
    monkeypatch.delitem(sys.modules, "t2_agentic_voice.api.cli")  # run afresh, as `python -m`
    with pytest.raises(SystemExit) as stopped:
        runpy.run_module("t2_agentic_voice.api.cli", run_name="__main__")
    assert stopped.value.code == 0
