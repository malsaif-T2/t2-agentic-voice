"""Importing the library configures nothing and prints nothing (the design's 3.3 and
10.2): in a child process with a clean environment, as a teammate's process first meets it,
every public module is imported, and a library line reaches an output only once the app adds a
handler or calls `configure_logging`."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from scripts.harness_config import load_config
from tests.isolation import dropped

ROOT = Path(__file__).resolve().parents[3]
# The child: what the root logger, the library's logger and structlog hold before and after the
# import, the lines logged before any handler, then an app's handler and `configure_logging`.
# It writes its report to the file it is given, so that its own output stays empty.
_CHILD = """
import importlib, io, json, logging, sys

root = logging.getLogger()
before = (list(root.handlers), root.level)
for module in json.loads(sys.argv[2]):
    importlib.import_module(module)
import structlog
from t2_agentic_voice import configure_logging, get_logger

library = logging.getLogger("t2_agentic_voice")
log = get_logger("t2_agentic_voice.probe")
report = {
    "root unchanged": (list(root.handlers), root.level) == before,
    "library": [type(h).__name__ for h in library.handlers] + [library.level],
    "webrtc levels": [logging.getLogger(n).level for n in ("aiortc", "aioice")],
    "structlog configured": structlog.is_configured(),
}
log.warning("unconfigured_warning", count=1)
log.error("unconfigured_error", count=2)
kept = []


class Kept(logging.Handler):
    def emit(self, record):
        kept.append([record.getMessage(), record.fields])


library.addHandler(Kept())
library.setLevel(logging.INFO)
log.info("app_line", count=3)
stream = io.StringIO()
configure_logging(stream=stream)
log.info("configured_line", count=4)
report["kept"], report["configured"] = kept, stream.getvalue()
with open(sys.argv[1], "w", encoding="utf-8") as out:
    json.dump(report, out)
"""


@pytest.fixture(scope="module")
def child(tmp_path_factory: pytest.TempPathFactory) -> tuple[bytes, bytes, dict[str, Any]]:
    """The child's standard output, its standard error, and its report. Its shell drops what
    the suite drops (tests/isolation.py) and every `PYTHON*` variable (a warnings filter, say),
    and it runs isolated in UTF-8 mode, so its error stream is not this machine's code page."""
    report = tmp_path_factory.mktemp("logging-import") / "report.json"
    modules = json.dumps(sorted(load_config(ROOT).arch.public))
    shell = {k: v for k, v in os.environ.items() if not dropped(k) and not k.startswith("PYTHON")}
    done = subprocess.run(
        [sys.executable, "-I", "-X", "utf8", "-c", _CHILD, str(report), modules],
        cwd=ROOT,
        env=shell,
        capture_output=True,
        timeout=120,
        check=False,
    )
    assert done.returncode == 0, done.stderr.decode("utf-8", errors="replace")
    return done.stdout, done.stderr, json.loads(report.read_text(encoding="utf-8"))


def test_importing_the_library_prints_nothing(child: tuple[bytes, bytes, dict[str, Any]]) -> None:
    """Not on import, and not a warning or an error logged before the app configured logging:
    the `NullHandler` keeps Python's last-resort handler from printing them."""
    out, err, _ = child
    assert (out, err) == (b"", b"")


def test_importing_the_library_configures_nothing(
    child: tuple[bytes, bytes, dict[str, Any]],
) -> None:
    """The root logger's handlers and level as they were, a `NullHandler` alone on the library's
    logger, with no level of its own, the WebRTC stack's untouched, and structlog unconfigured."""
    report = child[2]
    assert report["root unchanged"] is True
    assert report["library"] == ["NullHandler", 0]
    assert report["webrtc levels"] == [0, 0]
    assert report["structlog configured"] is False


def test_a_library_line_reaches_an_output_once_the_app_gives_it_one(
    child: tuple[bytes, bytes, dict[str, Any]],
) -> None:
    """An app's own handler on the library's logger gets the event and its fields; after
    `configure_logging`, the stream it was given gets the next line, and neither the lines
    logged before."""
    report = child[2]
    assert report["kept"] == [["app_line", {"count": 3}], ["configured_line", {"count": 4}]]
    (line,) = report["configured"].splitlines()
    assert "configured_line" in line and "count=4" in line and "unconfigured" not in line
