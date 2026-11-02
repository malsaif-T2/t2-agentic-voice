"""One call's session (the design's 12.2): built by plan 003's Track D; until then a stub.

In echo mode (`session.mode`, Q3) it greets the caller once connected, then says each turn back
in the voice of the call's language, one voice per reply: the cached frame first, once the
turn's transcript is in, then the heard words, clause by clause, while the text-to-speech
request runs; an empty transcript is said back as nothing and kept on the timeline. Speech that
starts while the echo plays, or within 300 ms after it ends, is not said back (plan 003's
decision log), so the agent never echoes its own voice. A client's `stop` drops the turn's reply
at once and the session listens again; `hangup` ends the call. It counts each model's usage, keeps
the call's `CallReport` and writes its numbers, with no text of the call, to a file under
`storage.var_dir`; traces each turn; records the call only when `privacy.record_audio` is on and
`allows_recording(setup.consent)` (core/identity.py) says the consent allows it (invariant 8);
and builds `HeardWords`, which only `voice` may build (invariant 1). It meets Pipecat only through
`io.py`. The recorder asks `allows_recording`, never the consent's class, and never copies or
rebuilds a consent: only adapters holds `CONSENT_SEAL` (`[[restricted]]`), and a `SignedConsent`
built or copied with a change anywhere else raises TypeError. Track D's test: with the setting
on, a plain `Consent` that says `record_audio` true keeps nothing.
"""

from __future__ import annotations

from t2_agentic_voice.voice.session.io import CallSetup, Commands, SessionEvent

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
