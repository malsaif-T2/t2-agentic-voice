"""One call's session (the design's 12.2): built by plan 003's Track D; until then a stub.

In echo mode (`session.mode`, Q3) it holds the whole call in its language (`setup.language`,
fixed at join), names it to the speech-to-text bridge (`ListenIn`), greets the caller once
connected (reply 0), then says each turn back in that language's voice, one voice per reply:
the cached frame first, once the turn's transcript is in, then the heard words, clause by
clause, while the text-to-speech request runs; an empty transcript is said back as nothing and
kept on the timeline. Each reply is the next from 0, its clauses keyed on it (io.py's replies).
A turn whose speech began while any reply played, the greeting included, or within 300 ms after
a reply's last clause played, is not said back (io.py's drop rule; plan 003's decision log), so
the agent never echoes its own voice. A client's `stop` drops at once every clause asked for so
far, whatever its reply (`StopSpeaking` naming the newest reply: io.py's stop path), each reply
it drops counted as done, and the session listens again; `hangup` ends the call. It tells the
caller of a failure, and of an end it chose, with the call language's notices
(`setup.language.notices`; domain/declaration.py's `NoticeKind`): `error` after a turn it would
say back whose transcript failed, or an echo one of whose clauses failed; `ended` when it ends
the call at a limit, `limits.max_call_s` or `limits.idle_s` (plan 003, Q4), hanging up once the
notice has played or failed, or at once when a stop drops it. Each goes out as a `notice`
message, whose text the client shows, and is spoken from the phrase cache as the next reply,
naming no turn; `busy` is admission control's, at join. Whatever ends the call, its `HangUp`
leaves a turn still open, or with its transcript still to come, unfinished (io.py's end).

It says the heard words as the agent's pronunciation map says them: it applies `pronounce`
(domain/text/pronounce.py) with `agent.pronounce`, in the call's language, to a reply's text
before it cuts it with `split_clauses` at `setup.max_chars`, so each clause is measured on the
said form; it gives each clause's `Speak` the text the provider is sent, `provider_text` of the
clause (domain/text/invisible.py), which is never longer; and the agent's caption shows the
said form, clause by clause. A fixed phrase is played from the phrase cache, which applied
the map itself, and captioned as written.

It counts each model's usage from each request's report (io.py's usage), a request the call's
end cancelled included, keeps the call's `CallReport` and writes its numbers, with no text of
the call, to a file under `storage.var_dir`, once the call's stream has ended (`aclose`);
traces each turn; records the call only when `privacy.record_audio` is on and
`allows_recording(setup.consent)` (core/identity.py) says the consent allows it (invariant 8);
and builds `HeardWords`, which only `voice` may build (invariant 1). It meets Pipecat only
through io.py and its events and commands. The recorder asks `allows_recording` of
`setup.consent` itself, the very object the identity source returned, never the consent's
class, and never copies or rebuilds a consent: only the instance the seal validated, unchanged
since, allows recording, so a copy of it (even with no change, and by any path: `copy.copy`, a
pickle, `Consent.model_copy`), a consent rebuilt, re-typed or rewritten in place, or one built
here keeps nothing; and only adapters/join_tokens.py gives the seal (`[[restricted]]`).

Track D's tests, beyond the plan's list: with the setting on, a plain `Consent` that says
`record_audio` true keeps nothing, and so does a copy of a verified consent that says it
(`copy.copy(consent)`, `Consent.model_copy(consent)`), while that consent itself keeps the
audio; a turn whose speech begins during the greeting is dropped, and every `Speak`, clause
event and caption of the greeting (reply 0, no turn) and of the turn's echo (the next reply,
naming the turn) has a key of its own; a reply holding a mapped term in Arabic gets the term's
Arabic form, its clauses measured on that form; a notice queued as reply N+1 behind echo N,
then a `stop`: one `StopSpeaking` naming reply N+1, no event of either reply, and the session
goes on to the next turn, while a stop that drops the `ended` notice gives `HangUp` at once; a
turn still open, or with its transcript still to come, at an `Ending`, a `TransportFailure`, a
`hangup` message or `limits.max_call_s` ends the call with `HangUp` at once (for the limit,
once its notice has played) and is kept in the report as unfinished, with no `Transcribed`
after it; an echo clause queued at an `Ending` gets no `ClausePlayed` or `ClauseFailed`, and
its reply ends as cut (`AgentSpeechEnded` with what played); `TurnClosed`, `Transcribing`
(`audio_s` 4.0) and an `Ending` give the Whisper model's usage one request, 4.0 s sent and
10.0 s billed, and a clause's `Synthesizing` before the end counts one text-to-speech request
and its characters (test_session_scenes.py plays the greeting's, the stop's, the end's and the
usage's events with a scripted session); a failed transcript and a failed echo clause each give
the `error` notice, sent and spoken from the phrase cache with no request; and at
`limits.idle_s` the `ended` notice plays, then `HangUp` with the reason `idle`.
"""

from __future__ import annotations

from t2_agentic_voice.voice.session.io import CallSetup, Commands
from t2_agentic_voice.voice.session.session_events import SessionEvent

_STUB = "the voice session is built by plan 003's Track D"


class CallSession:
    """One call's session: a `Session`, driven by the Pipecat side's events, answering with
    `commands`. Built when the call's offer is answered, cheaply and with no IO; it begins at
    the call's `Connected`, gives its last command with its `HangUp`, and finishes at
    `aclose`."""

    def __init__(self, setup: CallSetup, commands: Commands) -> None:
        raise NotImplementedError(_STUB)

    async def handle(self, event: SessionEvent) -> None:
        """Take one event, as the `Session` protocol says: return soon, never raise."""
        raise NotImplementedError(_STUB)

    async def aclose(self) -> None:
        """Finish the call once its stream has ended, as the `Session` protocol says: the
        report written, never raise."""
        raise NotImplementedError(_STUB)
