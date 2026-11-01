"""The answerers `poe eval` runs: `reference`, `groq`, and optionally `prototype-cache`.

Built by plan 002's Track E; until then a stub.
"""

from __future__ import annotations

from t2_agentic_voice import Settings

from ole5_voice.evals.runs import Answerer

_STUB = "answerers.py is built by plan 002's Track E"


def make_answerer(name: str, settings: Settings) -> Answerer:
    """The answerer called `name`, built from `settings`."""
    raise NotImplementedError(_STUB)
