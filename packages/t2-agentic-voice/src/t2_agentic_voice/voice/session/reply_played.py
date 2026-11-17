"""What of a reply had played when the caller's speech began over it (`UserTurnEnded.reply_played`,
D-116), for turn_book.py: an app that checks what the caller had heard before a turn said over a
reply (the lean flight agent's booking check, for a yes answered under
`interruptions.answer_yes_over_question`: yes_over_question.py) reads it from the events, since
that turn's `UserTurnEnded` goes out when its words are heard, before the reply's
`AgentSpeechEnded` when they come while it plays.
"""

from __future__ import annotations

from t2_agentic_voice.voice.session.playback import Playback
from t2_agentic_voice.voice.session.report import TurnLog


def played_before(playback: Playback, turn: TurnLog) -> str | None:
    """The clauses of the reply `turn`'s speech began over that had played whole, with audio,
    before it began, their captions joined as `AgentSpeechEnded.text` joins them; None for a
    turn begun over no reply."""
    reply = None if turn.over_reply is None else playback.reply(turn.over_reply)
    speech_at = turn.speech_at
    if reply is None or speech_at is None:
        return None
    played: list[str] = []
    for clause in reply.clauses:
        at = clause.played_at
        if at is None or at > speech_at or clause.cut_short or clause.audio_s <= 0:
            break
        played.append(clause.caption)
    return " ".join(played)
