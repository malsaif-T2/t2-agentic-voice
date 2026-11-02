"""One call's session (the design's 12.2): built by plan 003's Track D; until then a stub.

In echo mode (`session.mode`, Q3) it holds the whole call in its language (`setup.language`,
fixed at join), names it to the speech-to-text bridge (`ListenIn`), greets the caller once
connected (reply 0), then says each turn back in that language's voice, one voice per reply:
the cached frame first, once the turn's transcript is in, then the heard words, clause by
clause, while the text-to-speech request runs; an empty transcript is said back as nothing and
kept on the timeline. Each reply is the next from 0, its clauses keyed on it (io.py's replies).
A turn whose speech began while any reply played, the greeting included, or within 300 ms after
a reply's last clause played, is not said back (io.py's drop rule; plan 003's decision log), so
the agent never echoes its own voice. A client's `stop` drops the reply at once and the session
listens again; `hangup` ends the call. It tells the caller of a failure, and of an end it
chose, with the call language's notices (`setup.language.notices`; domain/declaration.py's
`NoticeKind`): `error` after a turn it would say back whose transcript failed, or an echo one of
whose clauses failed; `ended` when it ends the call at a limit, `limits.max_call_s` or
`limits.idle_s` (plan 003, Q4), hanging up once the notice has played or failed. Each goes out
as a `notice` message, whose text the client shows, and is spoken from the phrase cache as the
next reply, naming no turn; `busy` is admission control's, at join. It counts each model's
usage, keeps the call's `CallReport` and writes its numbers, with no text of the call, to a
file under `storage.var_dir`; traces each turn; records the call only when
`privacy.record_audio` is on and `allows_recording(setup.consent)` (core/identity.py) says the
consent allows it (invariant 8); and builds `HeardWords`, which only `voice` may build
(invariant 1). It meets Pipecat only through io.py and its events and commands. The recorder
asks `allows_recording`, never the consent's class, and never copies or rebuilds a consent: only
adapters holds `CONSENT_SEAL` (`[[restricted]]`), and a `SignedConsent` built or copied with a
change anywhere else raises TypeError.

Track D's tests, beyond the plan's list: with the setting on, a plain `Consent` that says
`record_audio` true keeps nothing; a turn whose speech begins during the greeting is dropped,
and every `Speak`, clause event and caption of the greeting (reply 0, no turn) and of the
turn's echo (the next reply, naming the turn) has a key of its own (test_session_fakes.py's
greeting scene shows the events); a turn still open, or with its transcript still to come, at
an `Ending` or a `TransportFailure` ends the call with `HangUp` at once and is kept in the
report as unfinished; a failed transcript and a failed echo clause each give the `error`
notice, sent and spoken from the phrase cache with no request; and at `limits.idle_s` the
`ended` notice plays, then `HangUp` with the reason `idle`.
"""

from __future__ import annotations

from t2_agentic_voice.voice.session.io import CallSetup, Commands
from t2_agentic_voice.voice.session.session_events import SessionEvent

_STUB = "the voice session is built by plan 003's Track D"


class CallSession:
    """One call's session: a `Session`, driven by the Pipecat side's events, answering with
    `commands`. Built when the call's offer is answered, cheaply and with no IO; it begins at
    the call's `Connected` and ends with its `HangUp`."""

    def __init__(self, setup: CallSetup, commands: Commands) -> None:
        raise NotImplementedError(_STUB)

    async def handle(self, event: SessionEvent) -> None:
        """Take one event, as the `Session` protocol says: return soon, never raise."""
        raise NotImplementedError(_STUB)
