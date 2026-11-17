"""The caller's turns as one call's session keeps them (voice/session/call.py), by number, each a
`TurnLog` (report.py): when its speech began and ended, whether it began over the agent's speech
(io.py's drop rule under `interruptions.mode = "drop"`, an overlap under `two_step`), its request
and its words heard, each counted (`usage`), traced (`trace`), recorded (`recorder`) and told to
the observers (`events`: a failed request's `ProviderFailed`, and the heard words of a turn not
dropped); what became of it, kept in the heard history (`history`: history.py's fates); and each
settled once it has closed, been heard and had its reply played, its trace ended then and its
times sent (none for a dropped turn's). A turn whose answer to a read-back waits for a chat
model's word (yes_ask.py: `judging`) takes no fate and does not settle until that word is
carried out or dropped (`judged`), so the reply its verdict says is the one it settles after.

Only a turn's `turn` transcript is its own: an overlap's `window` and `overlap` parts are counted
here, as every request is, and judged by the overlaps (overlap.py). A turn's transcript that
reuses its overlap's (no request of its own) is counted and told failed only as that request
was, so one request is never counted or reported twice. A transcript the filter for
text from silence takes for no words (domain/silence.py, under `stt.no_speech_max` and
`stt.caption_filter`, both on by default) is heard as nothing, so it is said back as nothing.

A turn's language is the one its first request named, whatever its part, and how it was chosen,
as that request's `Transcribing` says: in a call with a talker the held request decides the turn,
and a reused result hands no request of the turn's own; until a hold began, or once speech resumed
in it, each request of a turn that is no overlap names it anew (`turns.early_at_stop` sends one at
each stop). It is traced on the turn's speech-to-text span, with the verdict's share for a
classified turn only, and named in the call report (report.py).

A turn's time to first audio (plan 006), its reply's first audible frame sent, is turn_audio.py's
(`TurnAudio`, the base of `TurnBook`).
"""

from __future__ import annotations

from t2_agentic_voice.core.conversation import TurnFate
from t2_agentic_voice.core.events import TurnId
from t2_agentic_voice.core.yes_inputs import HeardWords
from t2_agentic_voice.domain.silence import CAPTIONS, from_silence
from t2_agentic_voice.voice.session.books import CallBooks
from t2_agentic_voice.voice.session.heard import heard_words
from t2_agentic_voice.voice.session.io import CallSetup
from t2_agentic_voice.voice.session.playback import Playback, Reply
from t2_agentic_voice.voice.session.reply_played import played_before
from t2_agentic_voice.voice.session.report import TurnLog
from t2_agentic_voice.voice.session.session_events import (
    HoldResumed,
    Transcribed,
    Transcribing,
    TurnClosed,
    TurnHeld,
    TurnOpened,
)
from t2_agentic_voice.voice.session.turn_audio import TurnAudio


class TurnBook(TurnAudio):
    """Every turn of one call, by its number, kept in the call's `books`; `listen` is the
    language the speech-to-text bridge names to the provider (none under
    `stt.live_language = "auto"`)."""

    def __init__(
        self, setup: CallSetup, books: CallBooks, *, listen: str | None, playback: Playback
    ) -> None:
        settings = setup.settings
        self._model, self._listen = settings.stt.model, listen
        self._usage, self._trace, self._recorder = books.usage, books.trace, books.recorder
        self._events, self._history = books.events, books.history
        self._playback = playback
        self._two_step = settings.interruptions.mode == "two_step"
        self._no_speech_max = settings.stt.no_speech_max
        self._captions = CAPTIONS if settings.stt.caption_filter else ()
        self._filter = self._no_speech_max is not None or settings.stt.caption_filter
        self._stop_s = settings.turns.vad_stop_ms / 1000
        self._turns: dict[TurnId, TurnLog] = {}

    def turn(self, turn_id: TurnId) -> TurnLog:
        known = self._turns.get(turn_id)
        if known is None:
            known = self._turns[turn_id] = TurnLog(turn_id=turn_id, stop_delay_s=self._stop_s)
        return known

    def opened(self, event: TurnOpened) -> Reply | None:
        """The turn opened: when its speech began, and whether that was over the agent's
        speech: dropped under the drop rule, or an overlap of the reply it began over, which is
        returned (None for any other turn)."""
        turn = self.turn(event.turn_id)
        turn.speech_at = event.speech_at
        over = self._playback.over(event.speech_at)
        turn.dropped = over is not None and not self._two_step
        turn.overlap = over is not None and self._two_step
        self._trace.turn_opened(event.turn_id)
        return over if turn.overlap else None

    def closed(self, event: TurnClosed) -> None:
        turn = self.turn(event.turn_id)
        turn.closed, turn.speech_ended_at = True, event.speech_ended_at
        turn.closed_at = event.at
        self.settle(turn)

    def hold(self, event: TurnHeld | HoldResumed) -> bool:
        """Smart Turn called the turn complete and its hold began (`TurnHeld`: True), its time
        kept; or the caller spoke again within it (`HoldResumed`: False), and that time, and the
        held request's transcript, no longer hold."""
        held, turn = isinstance(event, TurnHeld), self.turn(event.turn_id)
        turn.complete_at = event.at if held else None
        if not held:
            turn.held_heard_at = turn.language_by = None
        return held

    def transcribing(self, event: Transcribing) -> None:
        """A request of the turn went: counted, the first, or each before a hold, naming the
        turn's language (the module's); for its own transcript, its span opened too, but by a
        detecting request."""
        self._usage.transcribing(event)
        turn = self.turn(event.turn_id)
        anew = not turn.overlap and turn.complete_at is None and event.language_by != "detected"
        if turn.language_by is None or anew:
            turn.language, turn.language_by = event.language or self._listen, event.language_by
            turn.language_share = event.share
        if event.part != "turn" or event.language_by == "detected":
            return
        turn.requested = True
        by = None if turn.language_by == "session" else turn.language_by
        share = turn.language_share if by == "classified" else None
        self._trace.stt_sent(
            event.turn_id,
            model=self._model,
            language=turn.language,
            audio_seconds=event.audio_s,
            by=by,
            share=share,
        )

    def transcribed(self, event: Transcribed) -> tuple[TurnLog, HeardWords | None]:
        """The turn's own transcript came: counted, traced and recorded, a failure of its own
        request told, and the heard words told for a turn not dropped; the turn, and its heard
        words (None when nothing was heard, or when the filter takes the transcript for text from
        silence)."""
        turn, transcript = self.turn(event.turn_id), event.transcript
        turn.transcribed_at = event.at
        self._usage.transcribed(event)
        self._trace.stt_heard(
            event.turn_id,
            text="" if transcript is None else transcript.text,
            language=None if transcript is None else transcript.language,
            billed_seconds=None if transcript is None else transcript.billed_seconds,
        )
        heard = self._unless_silence(heard_words(event, speech_at=turn.speech_at), event)
        turn.heard = "" if heard is None else heard.text
        self._recorder.heard(event.at, event.turn_id, turn.heard, dropped=turn.dropped)
        if event.failure is not None and turn.requested:
            self._events.failed(event.failure, event.retryable, event.turn_id)
        if heard is not None:
            self._history.heard(heard)
        if turn.dropped:
            self.ended(turn, "dropped")
        else:
            self._events.heard(turn.turn_id, turn.heard, played_before(self._playback, turn))
        return turn, heard

    def held(self, event: Transcribed) -> HeardWords | None:
        """A turn's `held` transcript came (io.py's early start): counted, its request's
        failure told; its heard words, as `transcribed` would give them, kept nowhere."""
        self._usage.transcribed(event)
        if event.failure is not None:
            self._events.failed(event.failure, event.retryable, event.turn_id)
        else:
            self.turn(event.turn_id).held_heard_at = event.at
        speech_at = self.turn(event.turn_id).speech_at
        return self._unless_silence(heard_words(event, speech_at=speech_at), event)

    def _unless_silence(self, heard: HeardWords | None, event: Transcribed) -> HeardWords | None:
        """`heard`, or None when the filter is on and takes the transcript for text from
        silence (it is asked only when on, so a call with it off never reads the rule)."""
        if heard is None or not self._filter:
            return heard
        probability = None if event.transcript is None else event.transcript.no_speech_prob
        silent = from_silence(
            heard.text,
            probability,
            no_speech_max=self._no_speech_max,
            captions=self._captions,
        )
        return None if silent else heard

    def ended(self, turn: TurnLog, fate: TurnFate) -> None:
        """What became of `turn`, in its log and in the heard history; nothing yet while its
        answer is judged (`judging`)."""
        if turn.judging:
            return
        turn.fate = fate
        self._history.turn_ended(turn.turn_id, fate, reply_id=turn.reply_id)

    def judging(self, turn: TurnLog) -> None:
        """A chat model's word on `turn`'s answer to a read-back is awaited (yes_ask.py): until
        `judged`, the turn takes no fate and does not settle."""
        turn.judging = True

    def judged(self, turn: TurnLog, *, answered: bool) -> None:
        """The model's word on `turn` was carried out, or dropped: answered, when `answered`
        and no reply of its own answers it (as call.py marks a turn answered by nothing), then
        settled as any turn is, once its reply, if any, has played."""
        turn.judging = False
        if answered and turn.reply_id is None and turn.fate == "pending":
            self.ended(turn, "answered")
        self.settle(turn)

    def reply_ended(self, reply: Reply) -> None:
        """`reply` ended, however: the turn it answers settles, said back as the caller heard
        it, and answered (played whole, or ended by a clause's failure), cut (a stop or the
        call's end cut it after a clause played) or rolled back (before any did), unless it
        was already taken otherwise (a repeat request's turn stays a command)."""
        if reply.turn_id is None:
            return
        turn = self.turn(reply.turn_id)
        turn.stopped = turn.stopped or reply.stopped
        turn.tts_first_audio_s = reply.first_audio_s
        heard = self._history.reply(reply.reply_id)
        turn.said = heard.text
        if turn.fate == "pending" and turn.reply_id == reply.reply_id:
            fate: TurnFate = "answered"
            if reply.cut:
                played = any(clause.fate == "played" for clause in heard.clauses)
                fate = "cut" if played else "rolled_back"
            self.ended(turn, fate)
        self.settle(turn)

    def settle(self, turn: TurnLog) -> None:
        """Once a turn has closed, been heard and had its reply played, its trace ends and its
        times go out (none for a dropped turn); never while its answer is judged (`judging`)."""
        reply = None if turn.reply_id is None else self._playback.reply(turn.reply_id)
        if turn.done or turn.judging or not (turn.closed and turn.transcribed):
            return
        if reply is not None and reply.ended_at is None:
            return
        turn.done = True
        self._end_trace(turn)
        if not turn.dropped:
            self._events.metrics(turn, self._usage.report())

    @property
    def all_closed(self) -> bool:
        return all(turn.closed for turn in self._turns.values())

    @property
    def all_heard(self) -> bool:
        """Whether every turn has closed and its transcript has come (held_yes.py)."""
        return all(turn.closed and turn.transcribed for turn in self._turns.values())

    @property
    def awaited(self) -> bool:
        """Whether a turn to be answered has closed with its transcript still to come."""
        return any(turn.awaited for turn in self._turns.values())

    def end(self) -> None:
        """The call ended: every turn not yet heard is unfinished, as is every turn heard and
        not yet answered."""
        for turn in self._turns.values():
            turn.unfinished = not turn.transcribed
            if turn.unfinished or turn.fate == "pending":
                self.ended(turn, "unfinished")

    def close(self) -> list[TurnLog]:
        """The call's stream ended: each turn's trace not yet ended ends, with how it ended;
        every turn, for the report."""
        for turn in self._turns.values():
            if not turn.done:
                self._end_trace(turn)
        return list(self._turns.values())

    def _end_trace(self, turn: TurnLog) -> None:
        """The turn's trace ends, with its outcome, what was heard and what its reply said."""
        reply = None if turn.reply_id is None else self._playback.reply(turn.reply_id)
        said = "" if reply is None else reply.text
        self._trace.turn_ended(turn.turn_id, turn.outcome(), heard=turn.heard, said=said)
