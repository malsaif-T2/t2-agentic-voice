"""The `tracing` group: where spans go and what they hold (D-023). It names no API key: the
owner's Phoenix runs on this machine with no authentication (plan 003, the owner's decisions)."""

from __future__ import annotations

import re

from pydantic import Field, field_validator

from t2_agentic_voice.core.settings.base import Group, url


class TracingSettings(Group):
    """Tracing, as plain OTLP over HTTP to Phoenix or any OpenTelemetry backend (D-023)."""

    endpoint: str | None = Field(
        default=None,
        description=(
            "Where spans are sent: an OTLP/HTTP traces endpoint, such as a local Phoenix's "
            "http://127.0.0.1:6006/v1/traces. Unset: no span leaves the process, unless the app "
            "passes its own tracer provider."
        ),
    )
    project: str | None = Field(
        default=None,
        description="The project the spans are filed under in Phoenix. Unset: the default one.",
    )
    include_transcripts: bool = Field(
        default=True,
        description=(
            "Whether spans carry what was said: transcripts are the only call content a trace "
            "holds (docs/SECURITY.md, invariant 8)."
        ),
    )
    redact: tuple[str, ...] = Field(
        default=(),
        description=(
            "Regular expressions; every match is replaced in each text attribute before it is "
            'exported. A JSON list, such as ["\\\\d{10}"]. Unset: none.'
        ),
    )

    @field_validator("endpoint")
    @classmethod
    def _http(cls, value: str | None) -> str | None:
        return None if value is None else url(value, frozenset({"http", "https"}))

    @field_validator("redact")
    @classmethod
    def _patterns(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        for index, pattern in enumerate(value):
            if not _compiles(pattern):
                raise ValueError(
                    f"pattern {index} is not a regular expression Python's re module compiles"
                )
        return value


def _compiles(pattern: str) -> bool:
    """Whether `re` compiles `pattern`. Every error it may raise is caught here, and in no
    chain: `re.error`, whose text may quote the pattern (a group's name); an OverflowError, for
    a repetition count past the engine's limit; a RecursionError, for groups nested too deep;
    and any other. Raised in the validator, any but a ValueError would stop the load at once,
    uncollected, and a ValueError's text would reach the settings' error."""
    try:
        re.compile(pattern)
    except Exception:  # re.error, OverflowError, RecursionError and the like
        return False
    return True
