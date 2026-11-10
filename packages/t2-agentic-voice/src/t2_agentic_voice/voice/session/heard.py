"""The caller's heard words (docs/SECURITY.md, invariant 1), as the session takes them from the
turn's `Transcribed`: the only place they are built (core/yes_inputs.py holds the class, sealed,
so `domain`'s yes rule can read it). The echo says them back, and the yes rule takes them only
after a read-back's receipt, so no tool argument or model output can stand in for them.
"""

from __future__ import annotations

from t2_agentic_voice.core.yes_inputs import HEARD_WORDS_SEAL, HeardWords
from t2_agentic_voice.voice.session.session_events import Transcribed


def heard_words(event: Transcribed, *, speech_at: float | None) -> HeardWords | None:
    """The words the turn's transcript holds, `speech_at` when the caller began saying them
    (None when no turn opened for them); None when nothing was heard: the request failed, no
    audio was sent, or the transcript holds nothing but spaces."""
    transcript = event.transcript
    text = "" if transcript is None else transcript.text.strip()
    if transcript is None or not text:
        return None
    values = {
        "turn_id": event.turn_id,
        "text": text,
        "language": transcript.language,
        "at": event.at,
        "speech_at": speech_at,
        "source": event.source,
    }
    return HeardWords.model_validate(values, context=HEARD_WORDS_SEAL)


def with_text(heard: HeardWords, text: str) -> HeardWords:
    """`heard` holding only `text`, the words it said after a command."""
    values = {**heard.model_dump(), "text": text}
    return HeardWords.model_validate(values, context=HEARD_WORDS_SEAL)
