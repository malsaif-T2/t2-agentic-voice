"""A reply spoken while it is written (plan 006, "What voice-first means here", item 4): the
talker's, whose clauses come one by one while the model still writes and a tool may still run,
where `Speaker.say` takes every line up front (speaker.py; playback.py's `Playback.ask`).

The `Speaker` opens it (`open_reply`) before its first clause, so its cancel scope (scope.py) is
open for the talker's work from the start; each clause is added as it comes (`add_clause`),
asked for at once, keyed on the reply and its next index, and kept in the heard history
`unplayed` until it plays; a fixed phrase is added from the phrase cache (`add_phrase`: a
progress line, or the line said in a blocked clause's place); a card is shown (`card`), as
`t2v/1`'s `card`; and the reply is closed (`finish`) once its last clause and its work are done.
It ends, its scope cancelled, only once it is closed and its last clause has played or failed,
or at once when a stop or the call's end drops it (closed or not), as every reply ends
(speaker.py). A clause added after a stop dropped it is not asked for.

A clause is said as the echo says the heard words (echo.py's `said`): its numbers spoken by the
speaking rules (domain/text/speaking.py, after the output guard read its digits: the design's
8.2), the agent's pronunciation map applied in its language, and cut at the provider's
`max_chars`; a clause that fits one request is captioned as the talker wrote it, digits and all,
and one cut into several is captioned as said, part by part. A clause with nothing to say once
said is never sent.
"""

from __future__ import annotations

from typing import Protocol

from t2_agentic_voice.core.logging import get_logger
from t2_agentic_voice.core.settings.tts import LanguageTag
from t2_agentic_voice.domain.cards import Card
from t2_agentic_voice.domain.declaration import Language
from t2_agentic_voice.domain.ports.text_to_speech import AudioChunk
from t2_agentic_voice.domain.text.invisible import provider_text
from t2_agentic_voice.domain.text.speaking import speak_digits
from t2_agentic_voice.voice.protocol import ReplyId
from t2_agentic_voice.voice.session.echo import said
from t2_agentic_voice.voice.session.io import CallSetup
from t2_agentic_voice.voice.session.scope import CancelScope

_log = get_logger(__name__)


class ReplyWriter(Protocol):
    """What writes an open reply (speaker.py's `Speaker`): each clause asked for, a card shown,
    and the reply closed; each does nothing once the reply has ended."""

    async def write(
        self,
        reply_id: ReplyId,
        *,
        text: str,
        caption: str,
        language: LanguageTag,
        at: float,
        audio: AudioChunk | None = None,
        progress: bool = False,
    ) -> bool:
        """Ask for the reply's next clause; whether it was asked for."""

    async def show_card(self, reply_id: ReplyId, card: Card) -> bool:
        """Show `card`, as `t2v/1`'s `card`; whether it was shown."""

    async def close(self, reply_id: ReplyId, at: float) -> None:
        """The reply is written whole."""


def language_of(setup: CallSetup, tag: LanguageTag) -> Language:
    """The agent's language of `tag`, or the call's when the agent speaks no such language."""
    found = [each for each in setup.agent.languages if each.tag == tag]
    return found[0] if found else setup.language


def speech_of(setup: CallSetup, text: str, tag: LanguageTag) -> list[tuple[str, str]]:
    """`text`, a clause of the talker's in `tag`, as its requests say it: each request's text as
    the provider takes it and its caption (the module's docstring); none when it says nothing."""
    language = language_of(setup, tag)
    requests = said(
        speak_digits(text, language=tag),
        agent=setup.agent,
        language=language,
        max_chars=setup.max_chars(tag),
    )
    if len(requests) == 1:
        return [(provider_text(requests[0]), text.strip())]
    return [(provider_text(request), request) for request in requests]


def phrase_audio(setup: CallSetup, text: str, tag: LanguageTag) -> AudioChunk | None:
    """A fixed phrase's audio in `tag`'s voice, from the phrase cache; None, logged by its
    language alone, when the cache does not hold it (it then goes unsaid, and no request is
    sent for it)."""
    try:
        return setup.phrases.audio(text, language=tag)
    except LookupError:
        _log.warning("phrase_not_declared", language=tag)
        return None


class OpenReply:
    """A reply of the talker's, open while it is written: its number and its cancel scope,
    which the talker's work starts in, written by `writer` (the speaker) for the call `setup`
    gives."""

    def __init__(
        self,
        *,
        reply_id: ReplyId,
        scope: CancelScope,
        writer: ReplyWriter | None = None,
        setup: CallSetup | None = None,
    ) -> None:
        self.reply_id, self.scope = reply_id, scope
        self._writer, self._setup = writer, setup

    def _parts(self) -> tuple[ReplyWriter, CallSetup]:
        if self._writer is None or self._setup is None:
            raise RuntimeError("an open reply is opened by the speaker (Speaker.open_reply)")
        return self._writer, self._setup

    async def add_clause(self, text: str, *, language: LanguageTag, at: float) -> None:
        """Ask for the reply's next clause, `text` in `language`'s voice, at `at`; nothing once
        a stop or the call's end dropped the reply."""
        writer, setup = self._parts()
        for request, caption in speech_of(setup, text, language):
            if not await writer.write(
                self.reply_id, text=request, caption=caption, language=language, at=at
            ):
                return

    async def add_phrase(
        self, text: str, *, language: LanguageTag, at: float, progress: bool = False
    ) -> bool:
        """Ask for a fixed phrase, `text` in `language`'s voice, from the phrase cache, as the
        reply's next clause (`progress` for a progress line, timed apart); whether it was."""
        writer, setup = self._parts()
        audio = phrase_audio(setup, text, language)
        if audio is None:
            return False
        return await writer.write(
            self.reply_id,
            text=text,
            caption=text,
            language=language,
            at=at,
            audio=audio,
            progress=progress,
        )

    async def card(self, card: Card) -> None:
        """Show the caller `card`, as `t2v/1`'s `card`."""
        writer, _ = self._parts()
        await writer.show_card(self.reply_id, card)

    async def finish(self, at: float) -> None:
        """Close the reply at `at`: no clause follows, and its work is done, so it ends once its
        last clause has played (at once when it has none left to play)."""
        writer, _ = self._parts()
        await writer.close(self.reply_id, at)
