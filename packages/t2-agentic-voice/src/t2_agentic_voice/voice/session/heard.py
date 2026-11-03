"""The caller's heard words (docs/SECURITY.md, invariant 1): what speech-to-text heard in one of
the caller's turns, as the session takes it from the turn's `Transcribed`.

Heard words are the only words a later rule will take as the caller's own (the yes rule takes
them only after a read-back's receipt), so only `voice` builds them, from a speech-to-text
result: `[[restricted]]` (ARCH-CONSTRUCT) reports a `HeardWords` built in any other layer, and
no tool argument or model output can stand in for them. The echo says them back.
"""

from __future__ import annotations

from dataclasses import dataclass

from t2_agentic_voice.core.events import TurnId
from t2_agentic_voice.voice.session.session_events import Transcribed


@dataclass(frozen=True, kw_only=True)
class HeardWords:
    """The words speech-to-text heard in the caller's turn `turn_id`: `text`, with no space at
    either end; the `language` the provider heard or was told, in its code; and `at`, when the
    transcript came, on the call's clock."""

    turn_id: TurnId
    text: str
    language: str | None
    at: float


def heard_words(event: Transcribed) -> HeardWords | None:
    """The words the turn's transcript holds; None when nothing was heard: the request failed,
    no audio was sent, or the transcript holds nothing but spaces."""
    transcript = event.transcript
    text = "" if transcript is None else transcript.text.strip()
    if transcript is None or not text:
        return None
    return HeardWords(turn_id=event.turn_id, text=text, language=transcript.language, at=event.at)
