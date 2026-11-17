"""The flight agent's settings: its own under `FLIGHT_VOICE_`, and the library's under `T2V_`,
both read from the environment and, only when one is given, a `.env` file; the environment wins
over the file. This is the only module of the app that reads the environment.

The app's own (`AppSettings`, each field's description says what it does): the access code the
owner types on the page (required, at least 16 characters, made with `GENERATOR`), the website
allowed to frame the page, the token route's tokens a day (50), the airline's today (`live`, or
a date pinned), the mock airline's modes (its bookings' writes and lookup, its searches, its
profile, a slow read's seconds), the agent served (`agent`: `scripted`, today's, by default, or
`lean`, the model-led one beside it, D-113), and the persona's names, the owner's picks by
default (persona.py's `Names`).

`load` also, whatever else sets them:
- **nests the runtime's folder** under `<storage.var_dir>/flight` (`APP_FOLDER`): its used
  tokens, outbox, phrase cache and lock apart from Ole5's, since the runtime's lock allows one
  process a folder and both servers start with `--env-file .env`;
- **books up to 50 a caller a day** (`ACTIONS_PER_DAY`) unless the environment sets
  `limits.actions_per_caller_per_day`: a demo day books more than the library's default;
- **turns on** `guard.question_stop_drops_calls`, `guard.drop_stage_notes` and
  `guard.plain_speech` (`GUARD_ON`), sets `llm.max_requests_per_turn` to 4 (`REQUESTS_PER_TURN`),
  and, for the scripted agent alone, turns on `interruptions.yes_over_read_back`
  (`YES_OVER_READ_BACK`), each unless the environment sets it (run F's rounds 2 and 3): a
  question the limit stopped ends the turn with no call of its request run, a stage note or a
  tag the model writes is never said, nor a clause that is not speech, its request tried once
  more (D-111), a refused booking's next pick and its read-back fit in one turn, and a yes over
  the read-back books once its summary has played (D-108, the owner's "Any yes books"); the lean
  agent has no read-back to hold a yes over (`for_the_app`'s `agent`);
- **under `env` dev alone**, names the demo traveler the test console's dev caller, so a call the
  console starts is the traveler's, as a page's call is;
- **refuses a name that breaks the lines' rule** (persona.py's `breaking`), naming its setting.

A blank value counts as unset, as the library's do. The token route signs every token with the
join key `T2V_JOIN__CURRENT_KID` names, so that one is required too. Every failure is one
ConfigurationError naming each setting that cannot load, never its value, with a FIX line.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Final, Literal

from pydantic import Field, SecretStr, ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from t2_agentic_voice import (
    ConfigurationError,
    GuardSettings,
    InterruptionSettings,
    LimitSettings,
    LlmSettings,
    ServerSettings,
    StorageSettings,
    VoiceSettings,
)

from flight_voice.airline.bookings import Mode
from flight_voice.airline.system import SLOW_S, ProfileMode, SearchMode, live_today
from flight_voice.persona import Names, breaking
from flight_voice.traveler import demo_caller

# The app's prefix: one the library's settings never use.
PREFIX: Final = "FLIGHT_VOICE_"
# The app's own folder under the library's `storage.var_dir`.
APP_FOLDER: Final = "flight"
TOKENS_PER_DAY: Final = 50
ACTIONS_PER_DAY: Final = 50
# The library's guard settings the app turns on, its most model requests a turn, and its
# interruption setting it turns on, each unless set.
GUARD_ON: Final = ("question_stop_drops_calls", "drop_stage_notes", "plain_speech")
REQUESTS_PER_TURN: Final = 4
YES_OVER_READ_BACK: Final = "yes_over_read_back"
# The agent the app serves: today's scripted one, or the lean one beside it (D-113).
AgentKind = Literal["scripted", "lean"]
AGENTS: Final[tuple[AgentKind, ...]] = ("scripted", "lean")
MIN_ACCESS_CODE_CHARS: Final = 16
GENERATOR: Final = 'python -c "import secrets; print(secrets.token_urlsafe(24))"'
# A name: one line of at most 40 characters, with no control character, brace or dollar.
NAME_PATTERN: Final = r"^[^\x00-\x1f\x7f{}$]{1,40}$"
_DEFAULT: Final = Names()
_FIX: Final = (
    "FIX: set each one in the environment or the .env file given; make an access code with "
    f"{GENERATOR}."
)


def _name(default: str, what: str) -> str:
    return Field(default=default, pattern=NAME_PATTERN, description=what)


class AppSettings(BaseSettings):
    """The flight agent's own settings, read-only once loaded."""

    model_config = SettingsConfigDict(
        env_prefix=PREFIX,
        env_ignore_empty=True,
        extra="ignore",
        frozen=True,
        hide_input_in_errors=True,
    )

    access_code: SecretStr = Field(
        description="The code the owner types on the page to get a join token, at least 16 "
        "characters."
    )
    website_origin: str | None = Field(
        default=None,
        description="The website allowed to frame the page, an origin as a browser sends it "
        "(https://www.example.com). Unset: no page may frame it.",
    )
    tokens_per_day: int = Field(
        default=TOKENS_PER_DAY, ge=1, le=10_000, description="The join tokens minted a day."
    )
    today: Literal["live"] | date = Field(
        default="live",
        description="The airline's today: live (today in Riyadh at each read) or a date "
        "(2026-11-16) pinned.",
    )
    booking_mode: Mode = Field(
        default="answer",
        description="How the mock bookings store answers a write: answer, refuse, timeout (no "
        "reply, nothing done) or late (done, the reply late).",
    )
    booking_lookup: bool = Field(
        default=True, description="Whether the mock bookings store finds a write by its ID."
    )
    search_mode: SearchMode = Field(
        default="answer",
        description="How the mock airline answers a search, the fare calendar and the cabins: "
        "answer, fail or slow.",
    )
    profile_mode: ProfileMode = Field(
        default="answer", description="How the mock airline answers the profile: answer or fail."
    )
    slow_s: float = Field(
        default=SLOW_S, gt=0, le=30, description="How long a slow read of the airline waits."
    )
    agent: AgentKind = Field(
        default="scripted",
        description="The agent served: scripted (today's, with its read-back and yes rule) or "
        "lean (the model-led one beside it, D-113).",
    )
    persona_name_en: str = _name(_DEFAULT.persona_name_en, "The persona's name in English.")
    persona_name_ar: str = _name(_DEFAULT.persona_name_ar, "The persona's name in Arabic.")
    airline_name_en: str = _name(_DEFAULT.airline_name_en, "The airline's name in English.")
    airline_name_ar: str = _name(_DEFAULT.airline_name_ar, "The airline's name in Arabic.")
    airline_code: str = Field(
        default=_DEFAULT.airline_code,
        pattern=r"^[A-Z0-9]{2}$",
        description="The airline's two-character code, on cards and flight numbers; never "
        "said unless asked.",
    )
    airline_code_said_en: str = _name(_DEFAULT.airline_code_said_en, "The code said in English.")
    airline_code_said_ar: str = _name(_DEFAULT.airline_code_said_ar, "The code said in Arabic.")

    @field_validator("access_code")
    @classmethod
    def _long_enough(cls, value: SecretStr) -> SecretStr:
        code = value.get_secret_value().strip()
        if len(code) < MIN_ACCESS_CODE_CHARS:
            raise ValueError(f"holds fewer than {MIN_ACCESS_CODE_CHARS} characters")
        return SecretStr(code)

    @field_validator("website_origin")
    @classmethod
    def _an_origin(cls, value: str | None) -> str | None:
        if value is None:
            return None
        try:
            ServerSettings(allowed_origins=(value,))  # the library's rule for an origin
        except ValidationError:
            pass  # its errors hold the value: not chained
        else:
            return value
        raise ValueError(
            "is not an origin as a browser sends it: a lowercase scheme and host, and a port "
            "only when it is not the scheme's own"
        )

    def names(self) -> Names:
        """The persona's and the airline's names."""
        return Names.model_validate({f: getattr(self, f) for f in Names.model_fields})

    def today_source(self) -> Callable[[], date]:
        """What the airline reads today from: Riyadh's date now, or the date pinned."""
        pinned = self.today
        return live_today if pinned == "live" else lambda: pinned


@dataclass(frozen=True)
class Settings:
    """What the app runs with: its own settings, and the library's."""

    app: AppSettings
    voice: VoiceSettings


def load(env_file: Path | None = None) -> Settings:
    """The app's settings and the library's, from the environment and `env_file` when given, as
    the module's docstring says; ConfigurationError naming each setting that cannot load."""
    voice = VoiceSettings.from_env(env_file=env_file)
    refused: ConfigurationError | None = None
    try:
        app = AppSettings(_env_file=env_file, _env_file_encoding="utf-8")
    except ValidationError as error:
        refused = _cannot_load(error)
    if refused is not None:  # raised here, so no chain leads back to the values refused
        raise refused
    if voice.join.current_kid is None:
        name = voice.env_name("join", "current_kid")
        raise ConfigurationError(
            f"{name} is not set, and the token route signs every join token with that key. "
            f"FIX: set it to the ID of a key in {voice.env_name('join', 'keys')}.",
            details={"settings": [name]},
        )
    broken = [PREFIX + field.upper() for field in breaking(app.names())]
    if broken:
        raise ConfigurationError(
            f"{', '.join(broken)} would make a line the agent says hold a stop, wait, repeat, "
            "listening or send word, or a booking's claim. FIX: choose another name.",
            details={"settings": [*broken]},
        )
    return Settings(app=app, voice=for_the_app(voice, agent=app.agent))


def for_the_app(voice: VoiceSettings, *, agent: AgentKind = "scripted") -> VoiceSettings:
    """`voice` as the app runs `agent`: its folder nested (`APP_FOLDER`), its bookings a caller
    a day `ACTIONS_PER_DAY`, the guard's `GUARD_ON` on, its most requests a turn
    `REQUESTS_PER_TURN` and, for the scripted agent alone (the lean one has no read-back),
    `YES_OVER_READ_BACK` on, each unless set, and under `env` dev alone the demo traveler the
    test console's dev caller; every other setting as it was."""
    storage = StorageSettings.model_validate(
        voice.storage.model_dump() | {"var_dir": voice.storage.var_dir / APP_FOLDER}
    )
    update: dict[str, object] = {"storage": storage}
    if "actions_per_caller_per_day" not in voice.limits.model_fields_set:
        update["limits"] = LimitSettings.model_validate(
            voice.limits.model_dump() | {"actions_per_caller_per_day": ACTIONS_PER_DAY}
        )
    if on := {name: True for name in GUARD_ON if name not in voice.guard.model_fields_set}:
        update["guard"] = GuardSettings.model_validate(voice.guard.model_dump() | on)
    if agent == "scripted" and YES_OVER_READ_BACK not in voice.interruptions.model_fields_set:
        update["interruptions"] = InterruptionSettings.model_validate(
            voice.interruptions.model_dump() | {YES_OVER_READ_BACK: True}
        )
    if "max_requests_per_turn" not in voice.llm.model_fields_set:
        update["llm"] = LlmSettings.model_validate(
            voice.llm.model_dump() | {"max_requests_per_turn": REQUESTS_PER_TURN}
        )
    if voice.env == "dev":
        update["server"] = ServerSettings.model_validate(
            voice.server.model_dump() | {"dev_caller": demo_caller()}
        )
    return voice.model_copy(update=update)


def _cannot_load(error: ValidationError) -> ConfigurationError:
    """One error naming each setting of the app's that cannot load, never its value."""
    named = []
    for problem in error.errors(include_input=False, include_url=False):
        name = PREFIX + str(problem["loc"][0]).upper()
        why = problem["msg"].removeprefix("Value error, ")
        named.append((name, "is not set" if problem["type"] == "missing" else why))
    listed = "; ".join(f"{name} {why}" for name, why in named)
    return ConfigurationError(
        f"The flight agent's settings cannot load: {listed}. {_FIX}",
        details={"settings": [*sorted({name for name, _ in named})]},
    )
