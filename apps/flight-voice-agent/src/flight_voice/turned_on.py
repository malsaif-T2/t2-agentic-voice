"""The library's settings the flight app turns on for plan 010's first changes to how soon a call
answers, each unless the environment sets it, for settings.py's `for_the_app` (each is off in
the library by default, GP-18, until its measurement keeps it):

- **the warm-up** (row 1.13): the server's start imports a call's modules and makes its
  detectors ahead, each join sends its free warm requests, and the chat connection reopens after
  a cancel (`warmup.at_start`, `at_join`, `after_cancel`);
- **the end of a turn** (row 1.11, the owner's Q9), for an agent that reads its actions back
  (the scripted one) alone: a silence of 1.8 s ends a turn Smart Turn judged unfinished
  (`turns.max_silence_ms`), but while a read-back awaits its answer, when today's 3 s holds, so
  "yes, [pause] but change ..." is not cut after the yes (`turns.read_back_silence_ms`). The lean
  agent has no read-back, so its "Shall I book it?" would have no such exception, and any yes
  books (D-116): it keeps the library's 3 s for every turn until it has its own;
- **Smart Turn on two threads** (`turns.smart_turn_threads`; the study's rank 4): its model
  judged each pause in about 40 ms on 2 threads against 60 ms on 1 on this laptop, idle;
- **the beat after a progress line** (row 1.15): 0.1 s from the end of its speech before the
  answer (`session.progress_beat_ms`), the line itself said as its search starts (persona.py);
- **the early start from the detector's stop** (row 2.2): each turn's held request goes as the
  speech detector hears the caller stop, Smart Turn's time before its verdict, kept only when
  Smart Turn calls the turn finished (`turns.early_at_stop`), and a turn held while a reply to
  an earlier turn is still in progress starts early too, that reply stopped first
  (`session.early_over_reply`).
"""

from __future__ import annotations

from typing import Final

from t2_agentic_voice import VoiceSettings

MAX_SILENCE_MS: Final = 1800
READ_BACK_SILENCE_MS: Final = 3000
PROGRESS_BEAT_MS: Final = 100
SMART_TURN_THREADS: Final = 2
# Each group's settings the app turns on for either agent, by name, with their values.
TURNED_ON: Final[dict[str, dict[str, object]]] = {
    "warmup": {"at_start": True, "at_join": True, "after_cancel": True},
    "turns": {"smart_turn_threads": SMART_TURN_THREADS, "early_at_stop": True},
    "session": {"progress_beat_ms": PROGRESS_BEAT_MS, "early_over_reply": True},
}
# The turns' settings turned on for an agent that reads its actions back alone (the module's
# end of a turn).
READ_BACK_TURNS: Final[dict[str, object]] = {
    "max_silence_ms": MAX_SILENCE_MS,
    "read_back_silence_ms": READ_BACK_SILENCE_MS,
}


def turned_on(voice: VoiceSettings, *, read_back: bool) -> dict[str, object]:
    """Each group of `TURNED_ON`, with `READ_BACK_TURNS` for an agent that reads its actions
    back (`read_back`), as `voice` holds it, with each of its values the environment does not
    set; a group whose values it sets all is left out."""
    wanted = dict(TURNED_ON)
    if read_back:
        wanted["turns"] = TURNED_ON["turns"] | READ_BACK_TURNS
    found: dict[str, object] = {}
    for name, values in wanted.items():
        group = getattr(voice, name)
        unset = {key: value for key, value in values.items() if key not in group.model_fields_set}
        if unset:
            found[name] = type(group).model_validate(group.model_dump() | unset)
    return found
