"""The flight data's settings (`FlightDataFields`), a mixin of the app's own settings: the app's
`AppSettings` inherits them, so each is read under `FLIGHT_VOICE_` and `settings-ref` lists it;
this module reads nothing itself.

`refused_source(app)` names a source the settings cannot run, which `load` raises as it raises
its other checks: `serpapi` with no key (naming the setting, never a value), the scripted agent
on any source but the mock (it reads the mock airline alone), and `recorded` with no pinned
`FLIGHT_VOICE_TODAY` (a replay matches only the day it was recorded for). These are not model
validators: the app's settings error names each setting by its field's place, which a model
validator's error does not have.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Literal, Protocol

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings
from t2_agentic_voice import ConfigurationError

from flight_voice.voice_settings import PREFIX, AgentKind

__all__ = ["FlightDataFields", "Source", "refused_source"]

Source = Literal["mock", "recorded", "serpapi"]


class FlightDataFields(BaseSettings):
    """The flight data's settings (the module's docstring); no config of its own."""

    flight_data: Source = Field(
        default="mock",
        description="The flights the lean agent reads: mock (the mock airline), recorded "
        "(SerpApi's answers replayed from flight_data_fixtures) or serpapi (live, needs the "
        "key).",
    )
    serpapi_key: SecretStr | None = Field(
        default=None, description="SerpApi's key, for flight_data serpapi."
    )
    serpapi_deep_search: bool = Field(
        default=False,
        description="Whether SerpApi searches as Google Flights' page does (deep_search), slower.",
    )
    flight_data_deadline_s: float = Field(
        default=13.0,
        gt=0,
        le=30,
        description="How long one day's search may take, its retry included; the read timeout "
        "is one second less.",
    )
    flight_data_span_days: int = Field(
        default=14, ge=1, le=62, description="The most days of a span searched day by day."
    )
    flight_data_span_concurrency: int = Field(
        default=14, ge=1, le=16, description="The days of a span searched at once."
    )
    flight_data_span_deadline_s: float = Field(
        default=12.0,
        gt=0,
        le=30,
        description="How long a whole span may take; a day not answered by then is unknown.",
    )
    flight_data_cache_s: float = Field(
        default=600.0,
        ge=0,
        le=86_400,
        description="How long a live answer is kept for the same day asked again; 0 keeps none.",
    )
    flight_data_fixtures: Path | None = Field(
        default=None,
        description="The folder the recorded source replays from. Unset: the app's own "
        "(apps/flight-voice-agent/evals/flight_data).",
    )
    flight_data_record_to: Path | None = Field(
        default=None,
        description="With flight_data serpapi, a folder each answer is recorded into, without "
        "the key. Unset: nothing recorded.",
    )


class _Sourced(Protocol):
    """What `refused_source` reads of the app's settings."""

    @property
    def flight_data(self) -> Source: ...

    @property
    def serpapi_key(self) -> SecretStr | None: ...

    @property
    def agent(self) -> AgentKind: ...

    @property
    def today(self) -> Literal["live"] | date: ...


def _name(field: str) -> str:
    return PREFIX + field.upper()


def refused_source(app: _Sourced) -> ConfigurationError | None:
    """Why the settings cannot run their flight data source (the module's docstring), or None."""
    source, setting = app.flight_data, _name("flight_data")
    key = app.serpapi_key
    if source == "serpapi" and (key is None or not key.get_secret_value().strip()):
        name = _name("serpapi_key")
        return ConfigurationError(
            f"{setting} is serpapi but {name} is not set. FIX: set {name} to the SerpApi "
            f"key, or set {setting} to mock.",
            details={"settings": [setting, name]},
        )
    if source != "mock" and app.agent == "scripted":
        agent = _name("agent")
        return ConfigurationError(
            f"{setting} is {source} but {agent} is scripted, which reads the mock airline "
            f"alone. FIX: set {agent} to lean, or {setting} to mock.",
            details={"settings": [setting, agent]},
        )
    if source == "recorded" and app.today == "live":
        today = _name("today")
        return ConfigurationError(
            f"{setting} is recorded but {today} is live, and a replay matches only the day it "
            f"was recorded for. FIX: pin {today} to that day (2026-11-18).",
            details={"settings": [setting, today]},
        )
    return None
