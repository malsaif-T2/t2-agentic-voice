"""Each golden-set command, run as `python -m` runs it, prints its help for `--help` and does
nothing else (GP-17), whatever is built behind it."""

from __future__ import annotations

import runpy
import sys
import warnings

import pytest

COMMANDS = [
    "ole5_voice.evals.golden",
    "ole5_voice.evals.run",
    "ole5_voice.evals.compare",
    "ole5_voice.evals.history",
    "ole5_voice.evals.recorder",
    "ole5_voice.evals.split",
    "ole5_voice.evals.import_talkover",
    "ole5_voice.evals.import_recordings",
    "ole5_voice.evals.eot",
    "ole5_voice.evals.timing",
    "ole5_voice.evals.languages_run",
    "ole5_voice.evals.call_manifests",
    "ole5_voice.evals.overlap",
    "ole5_voice.evals.import_calls",
]


@pytest.mark.parametrize("module", COMMANDS)
def test_a_command_prints_its_help_and_runs_nothing(
    module: str, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(sys, "argv", [module, "--help"])
    with warnings.catch_warnings(), pytest.raises(SystemExit) as done:
        # runpy warns that the module was imported already, by the other tests.
        warnings.simplefilter("ignore", RuntimeWarning)
        runpy.run_module(module, run_name="__main__", alter_sys=True)
    assert done.value.code == 0
    assert capsys.readouterr().out.startswith("usage: ")
