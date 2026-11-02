"""The golden set's commands, run as their poe tasks run them (`python -m`), write their log lines
to standard output, stamped as the library stamps, and nothing to standard error. A command's
own logger is `__main__` then, not one under the app's package, so the app names both
(`ole5_voice.LOGGERS`); in-process tests import the module and cannot see it (plan 003, step 8).
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

from tests.isolation import dropped


def _broken_history(tmp_path: Path) -> list[str]:
    (source := tmp_path / "history.jsonl").write_bytes(b"{}\n")
    return ["--history", str(source), "--out", str(tmp_path / "page.md")]


@pytest.mark.parametrize(
    ("module", "argv", "event"),
    [
        ("compare", lambda tmp: [str(tmp / "r1"), str(tmp / "r2")], "comparison_not_made"),
        ("history", _broken_history, "history_not_rendered"),
    ],
)
def test_a_command_run_as_its_task_runs_it_logs_to_its_output(
    module: str,
    argv: Callable[[Path], list[str]],
    event: str,
    tmp_path: Path,
    new_process_logs: Callable[[str, str], str],
) -> None:
    """Each refuses, and says so in its one log line; its shell drops what the suite drops and
    every `PYTHON*` variable, and it runs isolated in UTF-8 mode."""
    shell = {k: v for k, v in os.environ.items() if not dropped(k) and not k.startswith("PYTHON")}
    done = subprocess.run(
        [sys.executable, "-I", "-X", "utf8", "-m", f"ole5_voice.evals.{module}", *argv(tmp_path)],
        cwd=tmp_path,
        env=shell,
        capture_output=True,
        timeout=120,
        check=False,
    )
    assert (done.returncode, done.stderr.decode("utf-8", errors="replace")) == (1, "")
    line = new_process_logs(done.stdout.decode("utf-8"), event)
    assert "[error" in line and "[__main__]" in line
