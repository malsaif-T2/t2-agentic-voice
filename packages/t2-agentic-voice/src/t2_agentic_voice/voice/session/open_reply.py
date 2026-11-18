"""A reply spoken while it is written (plan 006, "What voice-first means here", item 4): the
talker's, whose clauses come one by one while the model still writes and a tool may still run,
where `Speaker.say` takes every line up front (speaker.py; playback.py's `Playback.ask`).

The `Speaker` opens it (`open_reply`) before its first clause, so its cancel scope (scope.py) is
open for the talker's work from the start; each clause is added as it comes (`add_clause`),
asked for at once, keyed on the reply and its next index, and kept in the heard history
`unplayed` until it plays; a fixed phrase is added from the phrase cache (`add_phrase`: a
progress line, or the line said in a blocked clause's place); an action's line is added as a
clause is, a line of its read-back marked with its part (`add_line`); a card is shown (`card`), as
`t2v/1`'s `card`; and the reply is closed (`finish`) once its last clause and its work are done.
It ends, its scope cancelled, only once it is closed and its last clause has played or failed,
or at once when a stop or the call's end drops it (closed or not), as every reply ends
(speaker.py). A clause added after a stop dropped it is not asked for.

A clause is said as the echo says the heard words (echo.py's `said`): its numbers spoken by the
speaking rules (domain/text/speaking.py, after the output guard read its digits: the design's
8.2; in the caller's register, and its key combinations as their keys, when the
`tts.spoken_numbers` and `tts.spoken_key_combinations` settings ask), the agent's pronunciation
map applied in its language, and cut at the provider's `max_chars`; a clause that fits one
request is captioned as the talker wrote it, digits and all, and one cut into several is
captioned as said, part by part. A clause with nothing to say once
said is never sent.
"""

from __future__ import annotations

from typing import Protocol

from t2_agentic_voice.core.settings.tts import LanguageTag
from t2_agentic_voice.domain.action_lines import SpokenLine
from t2_agentic_voice.domain.cards import Card
from t2_agentic_voice.domain.declaration import Language
from t2_agentic_voice.domain.ports.text_to_speech import AudioChunk
from t2_agentic_voice.domain.text.arabic_numbers import Register
from t2_agentic_voice.domain.text.invisible import provider_text
from t2_agentic_voice.domain.text.keys import speak_keys
from t2_agentic_voice.domain.text.speaking import speak_digits
from t2_agentic_voice.domain.text.spoken_text import speak_text
from t2_agentic_voice.voice.protocol import ClauseIndex, ReplyId
from t2_agentic_voice.voice.session.echo import BEAT_S, beat_after, padded, phrase_audio, said
from t2_agentic_voice.voice.session.io import CallSetup
from t2_agentic_voice.voice.session.playback import ReadBackPart
from t2_agentic_voice.voice.session.scope import CancelScope


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
        part: ReadBackPart | None = None,
        talker: bool = False,
    ) -> ClauseIndex | None:
        """Ask for the reply's next clause (`talker` when the talker wrote it); its index,
        None when it was not asked for."""

    async def show_card(self, reply_id: ReplyId, card: Card) -> bool:
        """Show `card`, as `t2v/1`'s `card`; whether it was shown."""

    async def close(self, reply_id: ReplyId, at: float) -> None:
        """The reply is written whole."""


def language_of(setup: CallSetup, tag: LanguageTag) -> Language:
    """The agent's language of `tag`, or the call's when the agent speaks no such language."""
    found = [each for each in setup.agent.languages if each.tag == tag]
    return found[0] if found else setup.now.language


def speech_of(
    setup: CallSetup, text: str, tag: LanguageTag, register: Register | None = None
) -> list[tuple[str, str]]:
    """`text`, a clause of the talker's in `tag`, as its requests say it: each request's text as
    the provider takes it and its caption (the module's docstring); none when it says nothing.
    Its numbers are said in `register`, the caller's, when `tts.spoken_numbers` is
    `by_register` (domain/text/spoken_text.py), else as written; its key combinations as their
    keys when `tts.spoken_key_combinations` is on (domain/text/keys.py)."""
    language = language_of(setup, tag)
    tts = setup.settings.tts
    keyed = speak_keys(text, language=tag) if tts.spoken_key_combinations else text
    by_register = tts.spoken_numbers == "by_register"
    shaped = (
        speak_text(keyed, language=tag, register=register)
        if by_register
        else speak_digits(keyed, language=tag)
    )
    requests = said(
        shaped,
        agent=setup.agent,
        language=language,
        max_chars=setup.max_chars(tag),
    )
    if len(requests) == 1:
        return [(provider_text(requests[0]), text.strip())]
    return [(provider_text(request), request) for request in requests]


class OpenReply:
    """A reply of the talker's, open while it is written: its number and its cancel scope,
    which the talker's work starts in, written by `writer` (the speaker) for the call `setup`
    gives."""

    def __init__(
        self, *, reply_id: ReplyId, scope: CancelScope, writer: ReplyWriter, setup: CallSetup
    ) -> None:
        self.reply_id, self.scope = reply_id, scope
        self._writer, self._setup = writer, setup

    async def add_clause(
        self, text: str, *, language: LanguageTag, at: float, register: Register | None = None
    ) -> None:
        """Ask for the reply's next clause, `text` in `language`'s voice, at `at`, its numbers
        in the caller's `register` when the setting asks, marked the talker's (a streaming
        text-to-speech may say it on its socket); nothing once a stop or the call's end dropped
        the reply."""
        for request, caption in speech_of(self._setup, text, language, register):
            asked = await self._writer.write(
                self.reply_id, text=request, caption=caption, language=language, at=at, talker=True
            )
            if asked is None:
                return

    async def add_line(
        self,
        line: SpokenLine,
        *,
        language: LanguageTag,
        at: float,
        part: ReadBackPart | None = None,
    ) -> tuple[ClauseIndex, ...]:
        """Ask for an action's line (read_back.py, yes_turns.py), the read-back's `part` it
        says if any, as the reply's next clauses: its `spoken` form said as a clause is (a
        template, which the output guard does not check: the design's 8.2), captioned with its
        `text` when it fits one request; the indexes asked for, none once a stop or the call's
        end dropped the reply."""
        requests = speech_of(self._setup, line.spoken, language)
        captions = [line.text] if len(requests) == 1 else [caption for _, caption in requests]
        asked: list[ClauseIndex] = []
        for (request, _), caption in zip(requests, captions, strict=True):
            index = await self._writer.write(
                self.reply_id, text=request, caption=caption, language=language, at=at, part=part
            )
            if index is None:
                break
            asked.append(index)
        return tuple(asked)

    async def add_phrase(
        self,
        text: str,
        *,
        language: LanguageTag,
        at: float,
        progress: bool = False,
        beat_before: bool = False,
    ) -> bool:
        """Ask for a fixed phrase, `text` in `language`'s voice, from the phrase cache, as the
        reply's next clause (`progress` for a progress line, timed apart and followed by a beat
        of silence so the answer does not run into it: `session.progress_beat_ms` from the end
        of its speech when set; `beat_before` for a line said after the reply's words); whether
        it was."""
        audio = phrase_audio(self._setup, text, language, reply_id=self.reply_id)
        if audio is None:
            return False
        beat_ms = self._setup.settings.session.progress_beat_ms
        if progress and beat_ms is not None:
            audio = beat_after(audio, beat_ms / 1000)
        after_s = BEAT_S if progress and beat_ms is None else 0.0
        audio = padded(audio, before_s=BEAT_S if beat_before else 0.0, after_s=after_s)
        asked = await self._writer.write(
            self.reply_id,
            text=text,
            caption=text,
            language=language,
            at=at,
            audio=audio,
            progress=progress,
        )
        return asked is not None

    async def card(self, card: Card) -> None:
        """Show the caller `card`, as `t2v/1`'s `card`."""
        await self._writer.show_card(self.reply_id, card)

    async def finish(self, at: float) -> None:
        """Close the reply at `at`: no clause follows, and its work is done, so it ends once its
        last clause has played (at once when it has none left to play)."""
        await self._writer.close(self.reply_id, at)
