"""What the phrase cache's tests share (test_phrase_cache.py, test_phrase_cache_files.py): the
phrases of an English echo agent, a cache that declared one, the fake's take of a text, and
Track A's splitter and pronunciation map standing in by their contracts while each is still
Block 0's stub (`track_a`, an autouse fixture each test module imports), so these tests build
against no other track's unfinished code. Nothing here is a golden-set item's."""

from __future__ import annotations

import asyncio
import re
from pathlib import Path

import pytest
from t2_agentic_voice.adapters import phrase_cache
from t2_agentic_voice.adapters.phrase_cache import PhraseCache
from t2_agentic_voice.core.settings.tts import TtsSettings
from t2_agentic_voice.domain.declaration import Language, VoiceAgent
from t2_agentic_voice.domain.ports.text_to_speech import TextToSpeech
from t2_agentic_voice.domain.presets import NOTICES
from t2_agentic_voice.domain.text.clauses import split_clauses
from t2_agentic_voice.domain.text.pronounce import Pronunciations, pronounce

from tests.t2_agentic_voice.fakes import FakeTextToSpeech, tone

VOICES = TtsSettings().languages
GREETING = "Hello, and welcome to the made-up line."
ENGLISH = (
    GREETING,
    "I heard:",
    NOTICES["en"]["error"],
    NOTICES["en"]["cut_off"],
    NOTICES["en"]["ended"],
)
LINES = [f"Made-up line {word} ends." for word in ("one", "two", "three", "four", "five")]
LINES += [
    "Made-up line six ends.",
    "Made-up line seven ends.",
    "Made-up line eight ends here at last.",
]
LONG = " ".join(LINES)  # 204 characters, eight sentences


def _split(text: str, *, max_chars: int | None) -> tuple[str, ...]:
    """Track A's splitter for the texts here, by its contract: a clause ends at «،», «؟», «.»,
    and English punctuation; none of these texts holds a word longer than `max_chars`."""
    clauses = tuple(clause for clause in re.split(r"(?<=[.,?!،؟])\s+", text.strip()) if clause)
    assert max_chars is None or all(len(clause) <= max_chars for clause in clauses)
    return clauses


def _pronounce(text: str, pronunciations: Pronunciations, *, language: str) -> str:
    """Track A's map, by its contract: each written form standing as whole words replaced by
    how the language (by its primary code) says it."""
    code = "en" if language == "en" else "ar"
    for form, said in pronunciations.items():
        if code in said:
            text = re.sub(rf"(?<!\w){re.escape(form)}(?!\w)", said[code], text)
    return text


@pytest.fixture(autouse=True)
def track_a(monkeypatch: pytest.MonkeyPatch) -> None:
    """Track A's splitter and pronunciation map, standing in by their contracts while each is
    still Block 0's stub; once Track A merges, each is used as it is."""
    try:
        split_clauses("Made up.", max_chars=None)
    except NotImplementedError:
        monkeypatch.setattr(phrase_cache, "split_clauses", _split)
    try:
        pronounce("Made up.", {}, language="en")
    except NotImplementedError:
        monkeypatch.setattr(phrase_cache, "pronounce", _pronounce)


def english(greeting: str = GREETING, said: Pronunciations | None = None) -> VoiceAgent:
    """An English echo agent opening with `greeting`, its pronunciation map `said`."""
    return VoiceAgent(
        name="echo", languages=[Language.english(greeting=greeting)], pronounce=said or {}
    )


class Sleeps(list[float]):
    """The delays the cache waited, none of them slept."""

    async def __call__(self, seconds: float) -> None:
        self.append(seconds)


def declare(
    tts: TextToSpeech, folder: Path, agent: VoiceAgent, sleeps: Sleeps | None = None
) -> tuple[PhraseCache, int]:
    """A cache on `folder` that declared `agent`, and the requests it sent."""
    sleep = Sleeps() if sleeps is None else sleeps
    cache = PhraseCache(tts, folder=folder, voices=VOICES, _sleep=sleep)
    return cache, asyncio.run(cache.declare(agent))


def take(text: str, fake: FakeTextToSpeech) -> bytes:
    """What `fake` says for `text`, whole."""
    return tone(len(text) * fake.seconds_per_char, fake.sample_rate)
