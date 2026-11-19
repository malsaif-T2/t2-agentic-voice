"""The library's settings as the flight app runs them (`for_the_app`), the agents it serves
(`AgentKind`, `AGENTS`) and the app's prefix, apart from settings.py so the flight data's
settings (flight_data/settings.py) can name them with no import cycle; settings.py re-exports
every one of them, and its docstring says what `load` does with them.

`for_the_app` adds the booking's send words and `answer_yes_over_question` for the lean agent
only when it can book (`bookable`: the mock airline; on the real network the caller books on the
airline's own site, from the links on the cards, D-126, D-130).
"""

from __future__ import annotations

from typing import Final, Literal

from t2_agentic_voice import (
    GuardSettings,
    InterruptionSettings,
    LimitSettings,
    LlmSettings,
    ServerSettings,
    StorageSettings,
    VoiceSettings,
    WordSettings,
)

from flight_voice.app_voice import app_tts
from flight_voice.booking.lines import SEND_WORDS
from flight_voice.caller_register import REGISTER_WORDS
from flight_voice.traveler import demo_caller
from flight_voice.turned_on import turned_on

__all__ = [
    "ACTIONS_PER_DAY",
    "AGENTS",
    "APP_FOLDER",
    "GUARD_ON",
    "PREFIX",
    "REQUESTS_PER_TURN",
    "YES_OVER_QUESTION",
    "YES_OVER_READ_BACK",
    "AgentKind",
    "for_the_app",
]

# The app's prefix: one the library's settings never use.
PREFIX: Final = "FLIGHT_VOICE_"
# The app's own folder under the library's `storage.var_dir`.
APP_FOLDER: Final = "flight"
ACTIONS_PER_DAY: Final = 50
# The library's guard settings the app turns on, its most model requests a turn, and its
# interruption setting it turns on, each unless set.
GUARD_ON: Final = ("question_stop_drops_calls", "drop_stage_notes", "plain_speech", "retry_claims")
REQUESTS_PER_TURN: Final = 4
YES_OVER_READ_BACK: Final = "yes_over_read_back"
YES_OVER_QUESTION: Final = "answer_yes_over_question"
# The agent the app serves: today's scripted one, or the lean one beside it (D-113).
AgentKind = Literal["scripted", "lean"]
AGENTS: Final[tuple[AgentKind, ...]] = ("scripted", "lean")


def for_the_app(
    voice: VoiceSettings, *, agent: AgentKind = "scripted", bookable: bool = True
) -> VoiceSettings:
    """`voice` as the app runs `agent`: its folder nested (`APP_FOLDER`), its bookings a caller a
    day `ACTIONS_PER_DAY`, the guard's `GUARD_ON` on, its most requests a turn
    `REQUESTS_PER_TURN`, for the scripted agent `YES_OVER_READ_BACK` on and for the lean one
    (which has no read- back), when it can book, `YES_OVER_QUESTION`, with the booking's
    `SEND_WORDS` its `words.send`, `REGISTER_WORDS` for the caller's register, app_voice.py's
    speech, the calls' audio recorded where the caller consents, turned_on.py's `TURNED_ON` (and
    its `READ_BACK_TURNS` for the scripted agent), each unless set, and under `env` dev alone
    the demo traveler the console's dev caller; every other setting as it was."""
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
    books = agent == "lean" and bookable
    yes = YES_OVER_READ_BACK if agent == "scripted" else YES_OVER_QUESTION if books else None
    if yes is not None and yes not in voice.interruptions.model_fields_set:
        update["interruptions"] = InterruptionSettings.model_validate(
            voice.interruptions.model_dump() | {yes: True}
        )
    words = REGISTER_WORDS | ({"send": SEND_WORDS} if books else {})
    if unset := {k: v for k, v in words.items() if k not in voice.words.model_fields_set}:
        update["words"] = WordSettings.model_validate(voice.words.model_dump() | unset)
    if "max_requests_per_turn" not in voice.llm.model_fields_set:
        update["llm"] = LlmSettings.model_validate(
            voice.llm.model_dump() | {"max_requests_per_turn": REQUESTS_PER_TURN}
        )
    update["tts"] = app_tts(voice.tts)
    if "record_audio" not in voice.privacy.model_fields_set:  # the alpha keeps its calls' audio
        update["privacy"] = voice.privacy.model_copy(update={"record_audio": True})
    update |= turned_on(voice, read_back=agent == "scripted")
    if voice.env == "dev":
        update["server"] = ServerSettings.model_validate(
            voice.server.model_dump() | {"dev_caller": demo_caller()}
        )
    return voice.model_copy(update=update)
