"""The library's settings as the flight app runs them (`for_the_app`), the agents it serves
(`AgentKind`, `AGENTS`) and the app's prefix, apart from settings.py so the flight data's
settings (flight_data/settings.py) can name them with no import cycle; settings.py re-exports
every one of them, and its docstring says what `load` does with them.

`for_the_app` adds the booking's send words and `answer_yes_over_question` for the lean agent
only when it can book (`bookable`: the mock airline; on the real network the caller books on the
airline's own site, from the links on the cards, D-126, D-130); and it sends a request the
provider rejected once more (`llm.retry_rejected`, D-132; the owner's call of 2026-11-19, a tool
call the model wrote malformed that Groq refused) for either agent.

For either agent too, a clause the guard blocks is first sent again (the owner's calls of
2026-11-22, where a sum of two fares the model worked out itself was heard as «صار عندنا خلل
بسيط»): a request whose claim or whose number the guard held back is sent once more
(`retry_claims`, `retry_ids` in `GUARD_ON`), up to twice a turn (`_GUARD_SET`'s
`retries_per_turn`, unless set); a clause still blocked after that is told as the library
tells it, the caller hearing that something went wrong (the owner: "it should say it have
some difficulties"). The real network declares no booking claims (lean/choose.py).

For either agent too, each reply keeps the caller's language (the owner's calls of 2026-11-22,
where English small talk in an Arabic call was written in Arabic and read by the English
voice): every model request ends with a line naming the reply's language
(`llm.reply_line_always`; 15 plays of 5 switch dialogues, 8 of 30 switched turns in the wrong
language without it, 0 of 30 with it), and a short turn ("yes please", «إي») keeps the
language of the caller's last plain turn (`words.hold_reply_language`), each unless set.

The page may choose each call's speech-to-text, model and voice under Options (the owner's
request of 2026-11-22, choices.py): `server.call_choices` is on unless set, off in the library
(GP-18).
"""

from __future__ import annotations

from collections.abc import Mapping
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
GUARD_ON: Final = (
    "question_stop_drops_calls",
    "drop_stage_notes",
    "plain_speech",
    "retry_claims",
    "day_month_apart",
    "retry_ids",
)
# The guard's other values the app sets, each unless set (the module's docstring).
_GUARD_SET: Final[Mapping[str, object]] = {"retries_per_turn": 2}
# What keeps each reply in the caller's language, each unless set (the module's docstring): the
# line naming it at the end of every request, and a short turn's held.
_LANGUAGE_LLM: Final[dict[str, object]] = {"reply_line_always": True}
_LANGUAGE_WORDS: Final[dict[str, object]] = {"hold_reply_language": True}
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
    day `ACTIONS_PER_DAY`, the guard's `GUARD_ON` on and its `_GUARD_SET` values, its most
    requests a turn `REQUESTS_PER_TURN` and a rejected request sent once more
    (`llm.retry_rejected`), each reply kept in the caller's language (`_LANGUAGE_LLM`,
    `_LANGUAGE_WORDS`), for the scripted agent `YES_OVER_READ_BACK` on and for the lean one
    (which has no read-back), when it can book, `YES_OVER_QUESTION`, with the booking's
    `SEND_WORDS` its `words.send`, `REGISTER_WORDS` for the caller's register, app_voice.py's
    speech, the calls' audio recorded where the caller consents, turned_on.py's `TURNED_ON` (and
    its `READ_BACK_TURNS` for the scripted agent), the call choices the page offers under
    Options (`server.call_choices`, choices.py's `CALL_OPTIONS`), each unless set, and under
    `env` dev alone the demo traveler the console's dev caller; every other setting as it was."""
    storage = StorageSettings.model_validate(
        voice.storage.model_dump() | {"var_dir": voice.storage.var_dir / APP_FOLDER}
    )
    update: dict[str, object] = {"storage": storage}
    if "actions_per_caller_per_day" not in voice.limits.model_fields_set:
        update["limits"] = LimitSettings.model_validate(
            voice.limits.model_dump() | {"actions_per_caller_per_day": ACTIONS_PER_DAY}
        )
    guard: dict[str, object] = {**dict.fromkeys(GUARD_ON, True), **_GUARD_SET}
    if on := {k: v for k, v in guard.items() if k not in voice.guard.model_fields_set}:
        update["guard"] = GuardSettings.model_validate(voice.guard.model_dump() | on)
    books = agent == "lean" and bookable
    yes = YES_OVER_READ_BACK if agent == "scripted" else YES_OVER_QUESTION if books else None
    if yes is not None and yes not in voice.interruptions.model_fields_set:
        update["interruptions"] = InterruptionSettings.model_validate(
            voice.interruptions.model_dump() | {yes: True}
        )
    words = REGISTER_WORDS | _LANGUAGE_WORDS | ({"send": SEND_WORDS} if books else {})
    if unset := {k: v for k, v in words.items() if k not in voice.words.model_fields_set}:
        update["words"] = WordSettings.model_validate(voice.words.model_dump() | unset)
    model: dict[str, object] = {"max_requests_per_turn": REQUESTS_PER_TURN, "retry_rejected": True}
    model |= _LANGUAGE_LLM  # D-132, then the reply's language
    if llm := {k: v for k, v in model.items() if k not in voice.llm.model_fields_set}:
        update["llm"] = LlmSettings.model_validate(voice.llm.model_dump() | llm)
    update["tts"] = app_tts(voice.tts)
    if "record_audio" not in voice.privacy.model_fields_set:  # the alpha keeps its calls' audio
        update["privacy"] = voice.privacy.model_copy(update={"record_audio": True})
    update |= turned_on(voice, read_back=agent == "scripted")
    server: dict[str, object] = {}
    if "call_choices" not in voice.server.model_fields_set:  # the page's Options (choices.py)
        server["call_choices"] = True
    if voice.env == "dev":
        server["dev_caller"] = demo_caller()
    if server:
        update["server"] = ServerSettings.model_validate(voice.server.model_dump() | server)
    return voice.model_copy(update=update)
