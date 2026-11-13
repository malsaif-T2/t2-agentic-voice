"""What the phrase cache's tests share (test_phrase_cache.py, test_phrase_cache_files.py): the
phrases of an English echo agent, a cache that declared one, and the fake's take of a text.
Nothing here is a golden-set item's."""

from __future__ import annotations

import asyncio
from pathlib import Path

from t2_agentic_voice.adapters.phrase_cache import PhraseCache
from t2_agentic_voice.core.settings.tts import TtsSettings
from t2_agentic_voice.domain.declaration import Language, VoiceAgent
from t2_agentic_voice.domain.ports.text_to_speech import TextToSpeech
from t2_agentic_voice.domain.presets import NOTICES
from t2_agentic_voice.domain.text.pronounce import Pronunciations

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
