"""Invariant 8 for Pipecat's own log lines (voice/loguru_policy.py; plan 003, Q2): its loguru
namespace is off before voice first imports Pipecat, so in a new process, with loguru's default
sink in place, importing the library prints nothing, Pipecat's import banner included, and a
Pipecat DEBUG line holding what a caller said reaches no output, while a line of any other
module still does."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from types import FunctionType

from loguru import logger
from t2_agentic_voice.voice.loguru_policy import PIPECAT, switch_pipecat_off

from tests.isolation import child_shell

ROOT = Path(__file__).resolve().parents[3]
PRIVATE = "the caller said a private phrase"

# The child: import the library, then voice's modules that import Pipecat (its transport's
# import logs a DEBUG line of its own), then log a line as Pipecat's text-to-speech module
# does, holding a transcript, and one as the child's own module, which loguru's default sink
# prints.
_CHILD = f"""
import t2_agentic_voice
import t2_agentic_voice.voice.pipeline
from loguru import logger

pipecat_line = "from loguru import logger\\nlogger.debug('Generating TTS [{PRIVATE}]')"
as_pipecat = {{"__name__": "pipecat.services.tts_service"}}
exec(compile(pipecat_line, "tts_service.py", "exec"), as_pipecat)
logger.debug("a line of the child's own")
"""


def _line() -> None:
    """A DEBUG line, logged as whichever module the function is given as its globals."""
    logger.debug("a line")


def _child(code: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-I", "-X", "utf8", "-c", code],
        cwd=ROOT,
        env=child_shell(),
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=300,
        check=False,
    )


def test_importing_the_library_prints_nothing() -> None:
    done = _child("import t2_agentic_voice")
    assert done.returncode == 0 and (done.stdout, done.stderr) == ("", "")


def test_no_pipecat_line_reaches_loguru_s_default_sink() -> None:
    done = _child(_CHILD)
    assert done.returncode == 0, done.stderr
    assert "a line of the child's own" in done.stderr  # the default sink is in place
    assert PRIVATE not in done.stderr + done.stdout
    assert "Pipecat" not in done.stderr and "USERDATA_MAX_LENGTH" not in done.stderr


def test_a_sink_added_in_process_sees_no_pipecat_record() -> None:
    """Switched off (again, as at the runtime's start), Pipecat's namespace reaches no sink, an
    app's own included, while another module's lines do: loguru names a record by its caller's
    module, so the same function is run as a Pipecat module's and as an app's."""
    seen: list[str] = []
    sink = logger.add(lambda message: seen.append(message.record["name"] or ""), level="DEBUG")
    try:
        switch_pipecat_off()
        for module in (f"{PIPECAT}.pipeline.worker", "an_app"):
            FunctionType(_line.__code__, {"__name__": module, "logger": logger})()
    finally:
        logger.remove(sink)
    assert seen == ["an_app"]
