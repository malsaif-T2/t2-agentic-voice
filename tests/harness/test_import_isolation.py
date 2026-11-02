"""No variable from the shell is read when a package is imported during collection, before any
fixture runs: `groq` reads `GROQ_LOG` on import and `opentelemetry.context` reads
`OTEL_PYTHON_CONTEXT` (plan 002's step 2). This module imports both at its top, as Track B's
adapter and core's tracing do, and records what it saw then; tests/harness/test_isolation.py
runs it in a child whose shell sets both."""

from __future__ import annotations

import logging
import os

import groq  # noqa: F401  imported for what it reads on import
import opentelemetry.context  # noqa: F401  as above
from t2_agentic_voice.core.settings.base import PREFIX

WATCHED = ("GROQ_", "OTEL_", "PHOENIX_", PREFIX.upper())
# As pytest imported this module: the variables still set, and the levels `GROQ_LOG` would set.
SEEN_ON_IMPORT = sorted(n for n in os.environ if n.upper().startswith(WATCHED))
LEVELS_ON_IMPORT = {name: logging.getLogger(name).level for name in ("groq", "httpx")}
FIX = "FIX: make tests/conftest.py's pytest_configure drop them again, before collection."


def test_no_variable_from_the_shell_is_seen_on_import() -> None:
    assert SEEN_ON_IMPORT == [], f"Collection saw {SEEN_ON_IMPORT}. {FIX}"
    assert LEVELS_ON_IMPORT == {"groq": logging.NOTSET, "httpx": logging.NOTSET}, FIX
