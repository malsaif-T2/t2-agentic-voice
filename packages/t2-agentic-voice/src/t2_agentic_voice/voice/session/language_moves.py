"""How the session follows the caller into another of the agent's languages, under
`stt.live_language = "detected"` (D-038's amendment; the call's current language is
call_language.py's): `follow`, at each turn's own transcript that is no overlap (call.py)."""

from __future__ import annotations

from typing import Literal

from t2_agentic_voice.core.logging import get_logger
from t2_agentic_voice.core.yes_inputs import HeardWords
from t2_agentic_voice.voice.session.commands import ListenIn
from t2_agentic_voice.voice.session.io import CallSetup, Commands
from t2_agentic_voice.voice.session.report import TurnLog
from t2_agentic_voice.voice.session.session_events import Transcribed

_log = get_logger(__name__)

MovedBy = Literal["detected", "asked"]


async def follow(
    setup: CallSetup,
    commands: Commands,
    turn: TurnLog,
    heard: HeardWords | None,
    event: Transcribed,
) -> MovedBy | None:
    """Move the call when the turn `turn` (its transcript `event`, its heard words `heard`)
    moved it: a turn the detecting request heard in another of the agent's languages
    (`switched`; the speech-to-text bridge moved already), its record then naming that
    language, detected; or a spoken switch request (call_language.py's `asked`), the new
    language then named to the bridge (`ListenIn`). How the call moved, logged with the language
    alone; None when it did not."""
    now, transcript = setup.now, event.transcript
    by: MovedBy
    if event.switched and transcript is not None:
        moved, by = now.move(transcript.language), "detected"
        turn.language, turn.language_by = transcript.language, "detected"
    elif heard is not None and (asked := now.asked(heard.text)) is not None:
        moved, by = now.move(asked.tag), "asked"
        if moved is not None:
            await commands.run(ListenIn(language=moved.primary))
    else:
        return None
    if moved is None:
        return None
    _log.info("call_language_moved", call_id=setup.call_id, language=moved.tag, by=by)
    return by
