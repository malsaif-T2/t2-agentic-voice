"""The early start's request in one call's speech-to-text bridge (voice/stt_bridge.py; plan 006,
Q2): `HeldRequests`.

With `early` (a call with a talker: plan 006's early start), a turn that is no overlap whose hold
began (turn_hold.py's `TurnHeldFrame`) hands `TurnHeld` and sends its speech so far as its `held`
request at once, trimmed as the turn's own would be; speech resumed in the hold
(`HoldResumedFrame`) cancels that request, then hands `HoldResumed`. When no speech followed its
audio, the turn's own `Transcribed` is that request's result again, with no request (stt_turn.py's
`reused`). Each hold and each resume is told to the call's `languages`, whatever `early` says.

**At the detector's stop** (`at_stop`: `turns.early_at_stop`, plan 010's 2.2, only in a call with
the early start). The same request goes as the speech detector hears the turn's speech stop, Smart
Turn's time before its verdict, the turn's language decided then (`languages`): its `Transcribing`
is handed as it goes, its answer kept unhanded (`HeldTurn.ahead`). When Smart Turn calls the turn
complete, `TurnHeld` is handed and that request is the turn's `held` one, its `Transcribed` handed
as it comes, or at once when it came already; no request goes then. When Smart Turn calls the
pause unfinished (turn_hold.py's `TurnUnfinishedFrame`), the request is dropped, its answer never
handed, the language decided at the stop undone, and the next stop sends again with all the
turn's speech; speech resumed in the hold drops it, the `held` request that reuses it cancelled,
as above. A turn marked an overlap sends none, and one marked after its stop drops it. So a
turn's words are answered once: by the request its hold kept, or by its own. A dropped request is
never cancelled: it runs out unhanded, so its connection goes back to the provider's pool warm
for the next request (an HTTP/1.1 request cancelled in flight closes its connection, and the next
would pay a new handshake), and the call's end cancels it if it is still in flight
(`SttRequests.drop`).
"""

from __future__ import annotations

import asyncio

from pipecat.services.stt_service import STTService

from t2_agentic_voice.voice.session.session_events import HoldResumed, Transcribed, TurnHeld
from t2_agentic_voice.voice.session_bridge import EventStream
from t2_agentic_voice.voice.stt_language import TurnLanguages
from t2_agentic_voice.voice.stt_requests import SttRequests
from t2_agentic_voice.voice.stt_turn import HeldTurn


class HeldRequests:
    """The `held` requests of the bridge `processor` (its sample rate and its tasks), sent by
    `requests`, their events to `events`, each hold told to `languages`; `early`, the early
    start on, and `at_stop`, its request sent at the detector's stop; `trail_s`, the audio a
    request keeps after the detector's last stop (the module's)."""

    def __init__(
        self,
        processor: STTService,
        requests: SttRequests,
        events: EventStream,
        languages: TurnLanguages,
        *,
        early: bool,
        trail_s: float,
        at_stop: bool = False,
    ) -> None:
        self._processor, self._requests, self._events = processor, requests, events
        self._languages, self._early, self._trail_s = languages, early, trail_s
        self.at_stop = early and at_stop  # read by the pipeline's tests

    def stopped(self, turn: HeldTurn) -> None:
        """The detector heard the turn's speech stop: with `at_stop`, a turn that is no overlap
        and holds no `held` request decides its language and sends its speech so far now, the
        answer kept for Smart Turn's verdict (the module's)."""
        if not self.at_stop or turn.overlap is not None or turn.held is not None:
            return
        self._drop_ahead(turn)  # never so: each verdict keeps or drops the one before
        self._languages.held(turn, self._processor.sample_rate, began=True)
        turn.ahead, turn.ahead_starts = self._send(turn, hand=False), turn.starts

    def unfinished(self, turn: HeldTurn) -> None:
        """Smart Turn called the turn's pause unfinished: the request sent at its stop dropped,
        never answering, and the language decided then undone (the module's)."""
        if turn.ahead is not None:
            self._drop_ahead(turn)
            self._languages.held(turn, self._processor.sample_rate, began=False)

    async def hold(self, turn: HeldTurn, now: float, *, began: bool) -> None:
        """The turn's hold began (its `held` request sent, or the one sent at its stop kept) or
        resumed (its `held` request cancelled, the one sent at its stop dropped), in a call with
        the early start, for a turn that is no overlap (the module's); told to `languages` in
        every call."""
        self._languages.held(turn, self._processor.sample_rate, began=began)
        if not self._early or turn.overlap is not None:
            self._drop_ahead(turn)  # a turn marked an overlap after its stop
            return
        if began and turn.held is None:
            self._events.hand(TurnHeld(turn_id=turn.turn_id, at=now))
            ahead = turn.ahead
            if ahead is not None and turn.ahead_starts == turn.starts:
                turn.held = self._requests.reuse(ahead, "held")  # handed as it comes
                turn.held_starts = turn.ahead_starts
                return
            self._drop_ahead(turn)
            turn.held, turn.held_starts = self._send(turn), turn.starts
        elif not began and turn.held is not None:
            held, turn.held = turn.held, None
            await self._processor.cancel_task(held)  # with at_stop, a reuse, never the request
            self._drop_ahead(turn)
            self._events.hand(HoldResumed(turn_id=turn.turn_id, at=self._events.clock.now()))

    def _send(self, turn: HeldTurn, *, hand: bool = True) -> asyncio.Task[Transcribed]:
        """The turn's `held` request of its speech so far, trimmed as its own would be."""
        rate = self._processor.sample_rate
        audio = turn.request(int(self._trail_s * rate) * 2)
        voiced_s = turn.voiced_s(rate)
        return self._requests.send(turn.turn_id, audio, "held", voiced_s=voiced_s, hand=hand)

    @staticmethod
    def _drop_ahead(turn: HeldTurn) -> None:
        """The request sent at the turn's stop dropped, if any: never cancelled, it runs out
        unhanded, its connection kept warm, and the call's end cancels it (the module's)."""
        turn.ahead = None
