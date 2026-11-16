"""The answerers `poe eval` runs, by name: `reference` (`reference_answerer.py`), which gives each
variant its own reference and sends nothing, and one for each speech-to-text provider
(`stt_arms.ARMS`: `groq`, Whisper, and those measured beside it, D-100), each asking that
provider through the library's speech-to-text port, with its pacer and budget
(`groq_answerer.py`). Each answerer
lives in its own module; this one keeps what a run asks of any of them (`RunAnswerer`)
and builds the one a run names (`make_answerer`). The optional `prototype-cache` answerer, a
replay of the prototype's stored answers, is not built.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Mapping
from typing import Protocol

from t2_agentic_voice import Providers, VoiceSettings
from t2_agentic_voice.ports import SpeechToText
from t2_agentic_voice.tracing import Tracing

from ole5_voice.evals.groq_answerer import Budget, Clock, GroqAnswerer, Policy, Sleep
from ole5_voice.evals.models import Variant
from ole5_voice.evals.reference_answerer import ReferenceAnswerer
from ole5_voice.evals.runs import Answerer
from ole5_voice.evals.stt_arms import ARMS, recorded_model
from ole5_voice.evals.windows import Measure

ANSWERERS = ("reference", *ARMS)


class RunAnswerer(Answerer, Protocol):
    """An answerer as `poe eval` runs it. `spends`: it calls a provider, so its run needs a
    price and a cap and appends a history line; `needs_audio`: it reads the audio files."""

    spends: bool
    needs_audio: bool

    async def aclose(self) -> None:
        """Close what the answerer holds open."""


def adapter(settings: VoiceSettings) -> SpeechToText:
    """The speech-to-text adapter `stt.provider` names, built from the settings by the library
    (GP-22: a provider is swapped by a setting): ConfigurationError when its key is not set."""
    return Providers.speech_to_text(settings)


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
    """The answerer called `name`, built from `settings`: a provider's asks `stt`, by default
    the `adapter` of the settings, with no cap and no price unless `budget` gives them."""
    if name == "reference":
        return ReferenceAnswerer(measure)
    if name not in ARMS:
        raise ValueError(f"no answerer is called {name!r}; one of {', '.join(ANSWERERS)}")
    return GroqAnswerer(
        adapter(settings) if stt is None else stt,
        model=recorded_model(settings, name),
        policy=policy or Policy(),
        budget=budget or Budget(price_per_hour_usd=0.0),
        measure=measure,
        reuse=reuse or {},
        tracing=tracing,
        run_name=run_name,
        clock=clock,
        sleep=sleep,
        name=name,
        minimum_s=ARMS[name].minimum_s,
    )
