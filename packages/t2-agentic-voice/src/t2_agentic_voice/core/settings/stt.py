"""The `stt` group: speech-to-text."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from t2_agentic_voice.core.settings.base import Group

SttProvider = Literal["groq"]
SttModel = Literal["whisper-large-v3", "whisper-large-v3-turbo"]
# The language a live call sends Whisper: the session's, or none, for Whisper to detect.
LiveLanguage = Literal["session", "auto"]


class SttSettings(Group):
    """Speech-to-text: the adapter, the Whisper model, and how long a request may take."""

    provider: SttProvider = Field(
        default="groq",
        description="Which adapter turns speech into text; only Groq's exists for now (D-004).",
    )
    model: SttModel = Field(
        default="whisper-large-v3",
        description=(
            "The Whisper model: whisper-large-v3 or whisper-large-v3-turbo. The default stayed "
            "large-v3 on a registered measurement (D-025), and changes only on another (GP-18)."
        ),
    )
    timeout_s: float = Field(
        default=6.0,
        gt=0,
        allow_inf_nan=False,
        description="The longest one transcription request may take before it is a timeout.",
    )
    live_language: LiveLanguage = Field(
        default="session",
        description=(
            "The language a live call sends Whisper: session (the call's language, fixed when "
            "it joins from the caller's pick or the join token's locale) or auto (none, so "
            "Whisper detects it). A registered measurement sets the default (GP-18)."
        ),
    )
