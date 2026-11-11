"""A fake spoken-language classifier (domain/ports/language_classifier.py's `LanguageClassifier`)
for the tests of the session, the bridge and the wiring (plan 007's Block H): no model, no
thread of its own unless asked, each answer scripted.

Each entry of its script is one classification's answer: a mapping of shares by code (parsed at
the port, as an adapter's are), None for a busy classifier, a `ProviderError` to raise, or any
other object, handed back as it is (an answer that does not parse). With the script used up it
is unsure (an even split). It records each clip and the codes asked, waits on `gate` when one is
given (so a verdict stays in flight), then `delay_s` on the loop and `block_s` on a thread (as an
adapter's model runs), and keeps when each classification began and ended and whether one was
cancelled."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Mapping, Sequence

from t2_agentic_voice.core.errors import ProviderError
from t2_agentic_voice.domain.ports.language_classifier import LanguageScores
from t2_agentic_voice.domain.ports.speech_to_text import AudioClip

Answer = Mapping[str, float] | ProviderError | object | None
EVEN = {"ar": 0.5, "en": 0.5}


class FakeLanguageClassifier:
    """A `LanguageClassifier` that answers from a script (the module's docstring)."""

    name = "fake-classifier"

    def __init__(
        self,
        script: Sequence[Answer] = (),
        *,
        gate: asyncio.Event | None = None,
        delay_s: float = 0.0,
        block_s: float = 0.0,
        mass: float = 0.9,
    ) -> None:
        self.script = list(script)
        self.gate, self.delay_s, self.block_s, self.mass = gate, delay_s, block_s, mass
        self.calls: list[tuple[AudioClip, tuple[str, ...]]] = []
        self.loaded: list[tuple[str, ...]] = []
        self.began: list[float] = []
        self.ended: list[float] = []
        self.cancelled = 0
        self.closed = 0

    @property
    def answered(self) -> int:
        """How many classifications have come back."""
        return len(self.ended)

    async def load(self, among: Sequence[str]) -> None:
        self.loaded.append(tuple(among))

    async def classify(self, clip: AudioClip, *, among: Sequence[str]) -> LanguageScores | None:
        self.calls.append((clip, tuple(among)))
        self.began.append(time.monotonic())
        try:
            if self.gate is not None:
                await self.gate.wait()
            if self.delay_s:
                await asyncio.sleep(self.delay_s)
            if self.block_s:
                await asyncio.to_thread(time.sleep, self.block_s)
        except asyncio.CancelledError:
            self.cancelled += 1
            raise
        self.ended.append(time.monotonic())
        entry = self.script.pop(0) if self.script else EVEN
        if isinstance(entry, ProviderError):
            raise entry
        if entry is None:
            return None
        if isinstance(entry, Mapping):
            return LanguageScores.parsed(entry, among=among, mass=self.mass)
        return entry  # type: ignore[return-value]  # an answer that does not parse, on purpose

    async def aclose(self) -> None:
        self.closed += 1
