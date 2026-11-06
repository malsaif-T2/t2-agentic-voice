"""A reply spoken while it is written (plan 006, "What voice-first means here", item 4): the
talker's, whose clauses come one by one while the model still writes and a tool may still run,
where `Speaker.say` takes every line up front (speaker.py; playback.py's `Playback.ask`).

The `Speaker` opens it (`open_reply`) before its first clause, so its cancel scope (scope.py) is
open for the talker's work from the start; each clause is added as it comes (`add_clause`),
asked for at once, keyed on the reply and its next index, and kept in the heard history
`unplayed` until it plays; a card is shown (`card`), as `t2v/1`'s `card`; and the reply is
closed (`finish`) once its last clause and its work are done. It ends, its scope cancelled, only
once it is closed and its last clause has played or failed, or at once when a stop or the
call's end drops it (closed or not), as every reply ends (speaker.py). A clause added after a
stop dropped it is not asked for.

Plan 006's Track C builds it; this module holds its shape.
"""

from __future__ import annotations

from t2_agentic_voice.core.settings.tts import LanguageTag
from t2_agentic_voice.domain.cards import Card
from t2_agentic_voice.voice.protocol import ReplyId
from t2_agentic_voice.voice.session.scope import CancelScope


class OpenReply:
    """A reply of the talker's, open while it is written: its number and its cancel scope,
    which the talker's work starts in."""

    def __init__(self, *, reply_id: ReplyId, scope: CancelScope) -> None:
        self.reply_id, self.scope = reply_id, scope

    async def add_clause(self, text: str, *, language: LanguageTag, at: float) -> None:
        """Ask for the reply's next clause, `text` in `language`'s voice, at `at`; nothing once
        a stop or the call's end dropped the reply."""
        raise NotImplementedError("the streamed reply is plan 006's Track C")

    async def card(self, card: Card) -> None:
        """Show the caller `card`, as `t2v/1`'s `card`."""
        raise NotImplementedError("the streamed reply is plan 006's Track C")

    async def finish(self, at: float) -> None:
        """Close the reply at `at`: no clause follows, and its work is done, so it ends once its
        last clause has played (at once when it has none left to play)."""
        raise NotImplementedError("the streamed reply is plan 006's Track C")
