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
sent as the provider's text (`provider_text`, never longer) and captioned as said. No text built
from heard words is ever asked of the phrase audio (invariant 8).
"""

from __future__ import annotations

from dataclasses import dataclass

from t2_agentic_voice.core.events import TurnId
from t2_agentic_voice.core.logging import get_logger
from t2_agentic_voice.domain.declaration import Language, VoiceAgent
from t2_agentic_voice.domain.text.clauses import split_clauses
from t2_agentic_voice.domain.text.invisible import provider_text
from t2_agentic_voice.domain.text.pronounce import pronounce
from t2_agentic_voice.voice.protocol import ReplyId
from t2_agentic_voice.voice.session.commands import Speak
from t2_agentic_voice.voice.session.heard import HeardWords
from t2_agentic_voice.voice.session.io import CallSetup

_log = get_logger(__name__)
# The most text-to-speech requests one echo sends (the agent's bound, plan 003's decision log):
# at Orpheus's 200 characters, about 40 s of English said back, and under a third of Groq's
# published 10 requests a minute, so a transcript a hallucination made long cannot burst past it.
MAX_ECHO_REQUESTS = 3


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
    echo's frame), its audio from the phrase audio, captioned as written; None, logged by the
    language alone, when the phrase audio does not hold it, which the runtime's start declares
    (it then goes unsaid, and no request is sent for it)."""
    language = setup.language.tag
    try:
        audio = setup.phrases.audio(text, language=language)
    except LookupError:
        _log.warning("phrase_not_declared", language=language, reply_id=reply_id)
        return None
    speak = Speak(
        reply_id=reply_id, clause=0, turn_id=turn_id, text=text, language=language, audio=audio
    )
    return Line(speak=speak, caption=text)


def said(text: str, *, agent: VoiceAgent, language: Language, max_chars: int | None) -> list[str]:
    """`text` as the agent says it in `language`, one item a request: its pronunciation map
    applied, then cut into clauses of at most `max_chars` characters, each one that still says
    something once it is the provider's text, and the clauses packed greedily, in order, joined
    by a space, a request ended only where its next clause would pass `max_chars` (one request
    for no limit); none for a text with nothing to say."""
    spoken = pronounce(text, agent.pronounce, language=language.tag)
    requests: list[str] = []
    for clause in split_clauses(spoken, max_chars=max_chars):
        if not provider_text(clause).strip():
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
