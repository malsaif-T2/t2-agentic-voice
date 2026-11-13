"""The `tracing` group: where spans go and what they hold (D-023). It names no API key: the
owner's Phoenix runs on this machine with no authentication (plan 003, the owner's decisions)."""

from __future__ import annotations

from pydantic import Field, field_validator

from t2_agentic_voice.core.settings.base import Group, compiled, url


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
            "Whether spans carry what was said: what the caller was heard to say, the agent's "
            "replies and its tool calls with their results are the only call content a trace holds "
            "(docs/SECURITY.md, invariant 8)."
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
            if compiled(pattern) is None:
                raise ValueError(
                    f"pattern {index} is not a regular expression Python's re module compiles"
                )
        return value
