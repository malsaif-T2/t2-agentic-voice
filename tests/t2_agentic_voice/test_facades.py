"""The public facades (D-021): each module of [package] facades imports, exports exactly the
names plan 002 gives it, and defines none of them itself (ARCH-FACADE checks the source)."""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

from scripts.harness_config import load_config

ROOT = Path(__file__).resolve().parents[2]
# Every public name the facades hold; a name added to one is added here too, deliberately.
NAMES = {
    "t2_agentic_voice.ports": {"AudioClip", "DataFlow", "SpeechToText", "Transcript"},
    "t2_agentic_voice.groq": {"GroqSTT"},
    "t2_agentic_voice.languages": {
        "SpellingIssue",
        "SpellingRule",
        "normalize_arabic",
        "normalize_digits",
        "spelling_issues",
    },
    "t2_agentic_voice.evals": {
        "Recall",
        "cer",
        "id_recall",
        "sign_test",
        "silence_output",
        "term_recall",
        "wer",
    },
    "t2_agentic_voice.tracing": {"Redactor", "SpeechToTextSpan", "Tracing"},
}


def test_every_facade_is_listed_here() -> None:
    assert set(load_config(ROOT).arch.facades) == set(NAMES)


@pytest.mark.parametrize("facade", sorted(NAMES))
def test_a_facade_re_exports_its_names_from_the_layers(facade: str) -> None:
    module = importlib.import_module(facade)
    assert set(module.__all__) == NAMES[facade]
    for name in module.__all__:
        home = getattr(module, name).__module__
        assert home.startswith("t2_agentic_voice.") and home != facade, (name, home)
