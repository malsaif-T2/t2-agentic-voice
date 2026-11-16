"""What `VoiceCalls.start` (voice/calls.py) sets in the process before it warms its models. The
items cited are plan 003's appendix, "Changes to the plan's interfaces".

Pipecat's loguru namespace is switched off before voice first imports Pipecat (Q2, item 16); the
transport loggers are held at WARNING unless `logging.content` is on
(`core.logging.hold_transport_loggers`); `PIPECAT_SETUP_FILES` and `PIPECAT_SMART_TURN_LOG_DATA`
set to a value are refused (item 17), each named in a ConfigurationError, never its value. voice
reads no variable itself (ARCH-ENV): it asks `core.config.foreign_set`, which answers by name
however the settings were built.
"""

from __future__ import annotations

from t2_agentic_voice.core.config import VoiceSettings, foreign_set
from t2_agentic_voice.core.errors import ConfigurationError
from t2_agentic_voice.core.logging import hold_transport_loggers
from t2_agentic_voice.voice.loguru_policy import switch_pipecat_off

# Pipecat's variables that change what a call does whatever is passed in code: one executes the
# files it names in every pipeline, the other writes every turn's audio to disk (plan 003's
# appendix, item 17). `start` refuses either when set.
REFUSED_VARIABLES = ("PIPECAT_SETUP_FILES", "PIPECAT_SMART_TURN_LOG_DATA")


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
