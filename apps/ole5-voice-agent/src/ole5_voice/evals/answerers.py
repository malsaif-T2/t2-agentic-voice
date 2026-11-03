"""The answerers `poe eval` runs, by name: `reference` (`reference_answerer.py`), which gives each
variant its own reference and sends nothing, and `groq` (`groq_answerer.py`), which asks Groq's
Whisper through the library's speech-to-text port, with its pacer and budget. Each answerer
lives in its own module (TD-019); this one keeps what a run asks of any of them (`RunAnswerer`)
and builds the one a run names (`make_answerer`). The optional `prototype-cache` answerer, a
replay of the prototype's stored answers, is not built.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable, Mapping
from typing import Protocol

from t2_agentic_voice import VoiceSettings
from t2_agentic_voice.groq import GroqSTT
from t2_agentic_voice.ports import SpeechToText
from t2_agentic_voice.tracing import Tracing

from ole5_voice.evals.groq_answerer import Budget, Clock, GroqAnswerer, Policy, Sleep
from ole5_voice.evals.models import Variant
from ole5_voice.evals.reference_answerer import ReferenceAnswerer
from ole5_voice.evals.runs import Answerer
from ole5_voice.evals.windows import Measure

ANSWERERS = ("reference", "groq")
# The speech-to-text adapter of each `stt.provider` (GP-22: a provider is swapped by a setting).
_ADAPTERS: Mapping[str, Callable[[VoiceSettings], SpeechToText]] = {"groq": GroqSTT.from_settings}


class RunAnswerer(Answerer, Protocol):
    """An answerer as `poe eval` runs it. `spends`: it calls a provider, so its run needs a
    price and a cap and appends a history line; `needs_audio`: it reads the audio files."""

    spends: bool
    needs_audio: bool

    async def aclose(self) -> None:
        """Close what the answerer holds open."""


def adapter(settings: VoiceSettings) -> SpeechToText:
    """The speech-to-text adapter `stt.provider` names, built from the settings (Groq's:
    ConfigurationError when no key is set)."""
    return _ADAPTERS[settings.stt.provider](settings)


def make_answerer(
    name: str,
    settings: VoiceSettings,
    *,
    stt: SpeechToText | None = None,
    policy: Policy | None = None,
    budget: Budget | None = None,
    measure: Measure | None = None,
    reuse: Mapping[Variant, str] | None = None,
    tracing: Tracing | None = None,
    run_name: str = "run",
    clock: Clock = time.perf_counter,
    sleep: Sleep = asyncio.sleep,
) -> RunAnswerer:
    """The answerer called `name`, built from `settings`: `groq` asks `stt`, by default the
    `adapter` of the settings, with no cap and no price unless `budget` gives them."""
    if name == "reference":
        return ReferenceAnswerer(measure)
    if name != "groq":
        raise ValueError(f"no answerer is called {name!r}; one of {', '.join(ANSWERERS)}")
    return GroqAnswerer(
        adapter(settings) if stt is None else stt,
        model=settings.stt.model,
        policy=policy or Policy(),
        budget=budget or Budget(price_per_hour_usd=0.0),
        measure=measure,
        reuse=reuse or {},
        tracing=tracing,
        run_name=run_name,
        clock=clock,
        sleep=sleep,
    )
