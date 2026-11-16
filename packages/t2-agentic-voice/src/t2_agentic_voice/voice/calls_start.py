"""What `VoiceCalls.start` (voice/calls.py) sets in the process before it warms its models, the
modules it imports there, and how each call's detectors are made. The items cited are plan 003's
appendix, "Changes to the plan's interfaces".

- **Start.** The runtime's lifespan builds one `VoiceCalls` and starts it (`start`, which runs
  `warm`), which imports onnxruntime and warms one pair of models, a Silero VAD and a Smart Turn
  v3.2, each loading its ONNX model on the CPU there, never at import: importing onnxruntime
  takes 8 to 12 s a process (item 24). First it sets what `prepare` says, then imports in a
  thread the modules an offer needs (`import_call_modules`: Pipecat's pipeline, aiortc's peer),
  so the first offer does not wait 2 to 4 s for them on the event loop (TD-089), logging each
  part's time (`calls_warmed`). That import, and the detectors made ahead below, run only under
  `warmup.at_start` (core/settings/warmup.py: off by default until the warm-up's measurement
  keeps it, GP-18); off, the first offer imports the modules, as before.
- **The detectors.** Each call gets its own speech detector and turn analyzer, since each of
  Pipecat's keeps one stream's state (a `VADAnalyzer`'s buffer, Silero's model state, Smart
  Turn's audio) and its public constructor loads its own ONNX session, sharing none:
  `VoiceCalls` makes them with the factories it is given, and with none builds Silero and Smart
  Turn v3.2 from the settings' `turns` group, each loading its model again for the call (85.2
  to 134.2 ms each on the owner's machine). So it makes each pair off the event loop, one ahead
  (voice/spare.py's `Spare`) under `warmup.at_start`: the pair `start` warms is the first
  call's, and each call that takes one has the next made in the background, so no offer and no
  live call's audio waits for one. Off, `start` makes one pair and drops it (onnxruntime loaded),
  and each call's offer makes its own in a thread. A test gives fakes (a generated signal
  through a fake speech detector), through the runtime's private `_calls` (api/runtime.py);
  `start` warms the factories it is given, so a test's fakes load no ONNX model. With
  `turns.smart_turn` off, no turn analyzer is built: every pause ends a turn.

Pipecat's loguru namespace is switched off before voice first imports Pipecat (Q2, item 16); the
transport loggers are held at WARNING unless `logging.content` is on
(`core.logging.hold_transport_loggers`); `PIPECAT_SETUP_FILES` and `PIPECAT_SMART_TURN_LOG_DATA`
set to a value are refused (item 17), each named in a ConfigurationError, never its value. voice
reads no variable itself (ARCH-ENV): it asks `core.config.foreign_set`, which answers by name
however the settings were built.

`import_call_modules` imports what a call's offer needs (`CALL_MODULES`: the pipeline, Pipecat's
among it, and the peer, aiortc's), which took 2.1 to 4.2 s in a warm process and ran on the event
loop at the first offer (TD-089): `start` runs it in a thread, so the first caller waits for none
of it. This module imports none of them at its top, as voice/calls.py does not (GP-17).
"""

from __future__ import annotations

import asyncio
import importlib
from time import perf_counter

from t2_agentic_voice.core.config import VoiceSettings, foreign_set
from t2_agentic_voice.core.errors import ConfigurationError
from t2_agentic_voice.core.logging import get_logger, hold_transport_loggers
from t2_agentic_voice.voice.loguru_policy import switch_pipecat_off
from t2_agentic_voice.voice.spare import Spare

# Pipecat's variables that change what a call does whatever is passed in code: one executes the
# files it names in every pipeline, the other writes every turn's audio to disk (plan 003's
# appendix, item 17). `start` refuses either when set.
REFUSED_VARIABLES = ("PIPECAT_SETUP_FILES", "PIPECAT_SMART_TURN_LOG_DATA")
# What a call's offer imports (voice/calls.py's `answer`): imported at the start instead.
CALL_MODULES = ("t2_agentic_voice.voice.pipeline", "t2_agentic_voice.voice.transport")

log = get_logger(__name__)


async def warm[T](settings: VoiceSettings, spare: Spare[T]) -> None:
    """What `start` does (the module's docstring): `prepare`, the offer's modules imported (under
    `warmup.at_start`) and `spare` filled, each in a thread, and their times logged."""
    prepare(settings)
    began = perf_counter()
    if settings.warmup.at_start:
        await asyncio.to_thread(import_call_modules)
    imported = perf_counter()
    await spare.fill()
    log.info(
        "calls_warmed",
        at_start=settings.warmup.at_start,
        import_ms=elapsed_ms(began, imported),
        detectors_ms=elapsed_ms(imported),
    )


def prepare(settings: VoiceSettings) -> None:
    """Switch Pipecat's loguru off, refuse its variables that change every call, and hold the
    transport loggers unless `logging.content` is on (the module's docstring)."""
    switch_pipecat_off()
    refused = sorted(foreign_set(REFUSED_VARIABLES))
    if refused:
        raise ConfigurationError(
            f"Pipecat reads {' and '.join(refused)}, which change what every call does "
            "(one runs the files it names in each pipeline, the other writes every turn's "
            "audio to disk). FIX: unset it in the server's environment.",
            details={"variables": list(refused)},
        )
    if not settings.logging.content:
        hold_transport_loggers()


def import_call_modules() -> None:
    """Import `CALL_MODULES` (the module's docstring): run in a thread at the start."""
    for name in CALL_MODULES:
        importlib.import_module(name)


def elapsed_ms(began: float, ended: float | None = None) -> float:
    """The milliseconds from `began` to `ended` (now when None), on `perf_counter`, rounded."""
    return round(((perf_counter() if ended is None else ended) - began) * 1000, 1)
