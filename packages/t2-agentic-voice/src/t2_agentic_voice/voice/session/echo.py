"""What the echo session says (voice/session/call.py): each reply as the `Speak` commands of its
clauses, with the caption each clause shows as it plays.

A fixed phrase (the greeting, the echo's frame, a notice) is one clause, played from the phrase
audio the runtime made at its start (`PhraseAudio`), with no request, and captioned as written.
The heard words are said as the agent's pronunciation map says them in the call's language
(`pronounce`), cut by the clause splitter at the provider's `max_chars` on that said form, and the
clauses packed greedily, in order, into requests of at most `max_chars`, as the phrase cache packs
a fixed phrase: a turn of n characters costs about n / `max_chars` requests, not one a clause,
which at Groq's published 10 requests a minute would burst past it. An echo sends at most
`MAX_ECHO_REQUESTS`, its first; what is left goes unsaid, logged by number alone. Each request is
sent as the provider's text (`provider_text`, never longer) and captioned as said; a clause with
no letter or digit says nothing and is never sent (TD-060). A reply said again at the caller's
request (`again`) says each of its clauses as it did: a fixed phrase from the phrase audio, the
rest through text-to-speech as each was first sent, in its own language, so a clause the clause
cache kept (a talker's, never the echo's words) is found again. No text built from heard words is
ever asked of the phrase audio (invariant 8).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace

from t2_agentic_voice.core.events import TurnId
from t2_agentic_voice.core.logging import get_logger
from t2_agentic_voice.core.settings.tts import LanguageTag
from t2_agentic_voice.core.yes_inputs import HeardWords
from t2_agentic_voice.domain.declaration import Language, VoiceAgent
from t2_agentic_voice.domain.ports.text_to_speech import AudioChunk
from t2_agentic_voice.domain.text.clauses import split_clauses
from t2_agentic_voice.domain.text.invisible import provider_text
from t2_agentic_voice.domain.text.pronounce import pronounce
from t2_agentic_voice.domain.text.speaking import speak_arrows
from t2_agentic_voice.voice.protocol import ReplyId
from t2_agentic_voice.voice.session.commands import Speak
from t2_agentic_voice.voice.session.io import CallSetup

_log = get_logger(__name__)
# The most text-to-speech requests one echo sends (the agent's bound, plan 003's decision log):
# at Orpheus's 200 characters, about 40 s of English said back, and under a third of Groq's
# published 10 requests a minute, so a transcript a hallucination made long cannot burst past it.
MAX_ECHO_REQUESTS = 3
# The silence around a fixed line said next to other speech (a progress line, a notice), so one
# does not run into the other (D-077).
BEAT_S = 0.4


@dataclass(frozen=True, kw_only=True)
class Line:
    """One clause of a reply: the command that says it, and the caption it shows as it plays."""

    speak: Speak
    caption: str


def fixed(
    setup: CallSetup,
    text: str,
    *,
    reply_id: ReplyId,
    turn_id: TurnId | None = None,
) -> Line | None:
    """A fixed phrase of the call's language as the one clause of `reply_id` (its first, or the
    echo's frame), its audio from the phrase audio (`phrase_audio`), captioned as written; None
    when the phrase audio does not hold it."""
    language = setup.language.tag
    audio = phrase_audio(setup, text, language, reply_id=reply_id)
    if audio is None:
        return None
    speak = Speak(
        reply_id=reply_id, clause=0, turn_id=turn_id, text=text, language=language, audio=audio
    )
    return Line(speak=speak, caption=text)


def phrase_audio(
    setup: CallSetup, text: str, tag: LanguageTag, *, reply_id: ReplyId
) -> AudioChunk | None:
    """A fixed phrase's audio in `tag`'s voice, for reply `reply_id`, from the phrase audio, with
    no request; None, logged by the language and the reply's number alone, when the phrase audio
    does not hold it, which the runtime's start declares (it then goes unsaid, and no request is
    sent for it)."""
    try:
        return setup.phrases.audio(text, language=tag)
    except LookupError:
        _log.warning("phrase_not_declared", language=tag, reply_id=reply_id)
        return None


def padded(audio: AudioChunk, *, before_s: float = 0.0, after_s: float = 0.0) -> AudioChunk:
    """`audio` with silence before and after it."""
    before, after = (bytes(2 * round(s * audio.sample_rate)) for s in (before_s, after_s))
    return audio.model_copy(update={"pcm16": before + audio.pcm16 + after})


def said(text: str, *, agent: VoiceAgent, language: Language, max_chars: int | None) -> list[str]:
    """`text` as the agent says it in `language`, one item a request: its arrows said as a
    word (`speak_arrows`), its pronunciation map applied, then cut into clauses of at most
    `max_chars` characters, and the clauses packed
    greedily, in order, joined by a space, a request ended only where its next clause would pass
    `max_chars` (one request for no limit); none for a text with nothing to say. Only a clause
    with a letter or a digit is kept, none of which `provider_text` drops, so every request
    still says something as the provider's text: a clause of symbols alone ("♪", which
    Whisper writes on noise), or of joiners and direction marks, is never one (TD-060)."""
    arrows = speak_arrows(text, language=language.tag)
    spoken = pronounce(arrows, agent.pronounce, language=language.tag)
    requests: list[str] = []
    for clause in split_clauses(spoken, max_chars=max_chars):
        if not any(character.isalnum() for character in clause):
            continue
        if requests and (max_chars is None or len(requests[-1]) + 1 + len(clause) <= max_chars):
            requests[-1] = f"{requests[-1]} {clause}"
        else:
            requests.append(clause)
    return requests


def echo(setup: CallSetup, heard: HeardWords, *, reply_id: ReplyId) -> list[Line]:
    """The echo of the turn `heard`: the call language's cached frame, then the heard words as
    said, each packed request a clause of the reply, at most `MAX_ECHO_REQUESTS`; none when the
    words say nothing once said, so an empty turn is said back as nothing."""
    language = setup.language
    max_chars = setup.max_chars(language.tag)
    requests = said(heard.text, agent=setup.agent, language=language, max_chars=max_chars)
    if not requests:
        return []
    if len(requests) > MAX_ECHO_REQUESTS:
        _log.info("echo_cut", reply_id=reply_id, requests=len(requests), sent=MAX_ECHO_REQUESTS)
        requests = requests[:MAX_ECHO_REQUESTS]
    turn = heard.turn_id
    frame = fixed(setup, language.echo_frame, reply_id=reply_id, turn_id=turn)
    lines = [] if frame is None else [frame]
    for index, request in enumerate(requests, start=len(lines)):
        speak = Speak(
            reply_id=reply_id,
            clause=index,
            turn_id=turn,
            text=provider_text(request),
            language=language.tag,
        )
        lines.append(Line(speak=speak, caption=request))
    return lines


def again(
    setup: CallSetup,
    clauses: Sequence[tuple[str, str, LanguageTag | None, bool]],
    *,
    reply_id: ReplyId,
    turn_id: TurnId | None,
) -> list[Line]:
    """A reply said again at the caller's request, as reply `reply_id` answering `turn_id`: each
    of its `clauses` in order, given as its caption, the text its request sent, its language
    (None: the call's) and whether it was a fixed phrase. A fixed phrase plays from the phrase
    audio as `fixed` plays it (none, logged, when the phrase audio lacks it); any other clause
    sends the text it first sent, in its own language, captioned as before, so no heard words
    reach the phrase audio (invariant 8)."""
    tag = setup.language.tag
    lines: list[Line] = []
    for caption, sent, language, cached in clauses:
        index = len(lines)
        if cached:
            line = fixed(setup, caption, reply_id=reply_id, turn_id=turn_id)
            if line is not None:
                lines.append(replace(line, speak=replace(line.speak, clause=index)))
            continue
        spoken = language or tag
        speak = Speak(reply_id=reply_id, clause=index, turn_id=turn_id, text=sent, language=spoken)
        lines.append(Line(speak=speak, caption=caption))
    return lines
