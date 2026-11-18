"""The talker in the call (plan 006): how one call's session answers a turn with its talker
(agent/talker.py's `Talker`, the call's `CallSetup.talker`) instead of the echo, for
voice/session/call.py.

- **One reply, one scope** (D-060; "What voice-first means here", item 7). Each answer is the
  talker's reply to one `TalkerTurn`, built from the heard history (history.py's
  `conversation`: what the caller heard, clause by clause). The reply is opened on the speaker
  before its first clause (`Speaker.open_reply`, open_reply.py), and the talker runs in its
  cancel scope, on a task the scope holds, so a stop or the call's end cancels the model's
  request, the search and the speech at once. A turn answered while a reply to an earlier turn is
  in progress (said while the agent was silent, or while a search ran with nothing playing) stops
  that reply first, its work cancelled, so the talker starts again with both turns, the earlier
  one in the history as it ended (`rolled_back` when none of its reply played: then one turn).
- **Its events, in order** (agent/talker.py; each played by talker_play.py): a clause is said
  (`SpokenClause`, in its language, open_reply.py's speech); a card is shown (`ShownCard`, `t2v/1`'s
  `card`); a tool's start and end are the public `ToolStarted` and `ToolFinished`, and while the
  talker or a tool works with nothing left to play the agent is `thinking` (playback.py); a progress
  line is said from the phrase cache in its language (`ProgressDue`, timed apart: **the progress
  line** below); an action's read-back is said, and the call is confirming (`ReadBackRequested`,
  read_back.py); a clause the guard blocked is never said (`ClauseBlocked`): the reply's failure
  line is said in its place, once a reply (the preset's `error` notice when none of the reply was
  said, else `cut_off` after a beat: D-077), but for a claim whose request the talker sends once
  more (`sent_again`, `guard.retry_claims`), and `GuardBlocked` goes out (the talker keeps its
  developer note: the history holds only what the caller heard); each model request is
  counted in the call's usage as it goes and its tokens as it ends (`ModelRequested`,
  `ModelReplied`; an early start's or a kept reply's, dropped unplayed, once it is let go), the
  first one's first token the turn's; and the reply is closed once it is done (`ReplyDone`), the
  `error` notice said first when it said no clause (a model's empty answer, or one cut at its limit
  before a word), once a reply, so the caller never hears silence after asking. A talker that fails
  is logged by its failure's kind alone, a provider's failure told (`ProviderFailed`), and the
  caller hears the failure line, once a reply (`error` when none of the reply was said, else
  `cut_off`), in the reply's language (its last clause's, else the turn's as agent/language.py
  reads it); the reply is closed.
- **The early start** (plan 006, Q2; io.py's early start). A turn's `held` transcript starts the
  talker at once, in a scope of its own, while the hold runs: what it gives is kept, and nothing
  is asked for. Speech that resumes in the hold cancels it (`resumed`). When the hold ends (the
  turn's `TurnClosed`), the reply is opened in that scope (`release`), what was kept is played
  in order, each event guarded as one the talker gives later (a failure logged, the rest still
  played, the reply closed), and the rest as it comes; the turn's own transcript then finds it
  answering. Once the call has ended or is ending (its `ended` notice) nothing kept plays: the
  work is cancelled. A client's `stop` in the hold cancels the work too (`stopped`), and the
  turn is answered by nothing (`rolled_back`: the reply it began was stopped before any
  played). While a reply to an earlier turn is in progress there is no early start, since the
  talker would read the call before `answer` stops that reply (TD-117), unless
  `session.early_over_reply`: then the held words stop it first, as `answer` would, while the
  call is not confirming, and the talker starts on the call as it then stands.
- **The kept reply** (plan 006, Q19). While a newer turn of the caller's is open and not yet
  taken, nothing more of a reply to an earlier turn plays, what its talker gives kept: kept_reply.py
  (`KeptReplies`, the base of `Talking`).
- **The progress line** (plan 006, Q27). A `ProgressDue` with an `after_s` waits, in the reply's
  scope, until that long after the caller stopped speaking, whether the search or the model holds
  the reply up by then, and is said only if no clause has been asked of the voice by then, the reply
  is not kept and no notice took its place; past that time it is said at once, and once a clause was
  asked for, or kept behind it, never (talker_progress.py). With no `after_s`, said as it comes.
- **An answer to an action's read-back** (plan 007; yes_turns.py). While the call is confirming,
  a turn whose speech began once the read-back's summary played its last clause is the yes
  rule's, never the talker's, and starts no talker early (call.py); the talker answers it only
  when the rule declines the action, as a no or a correction (`TalkerTurn.declined`); a client's
  stop cancels a chat model's word on it still awaited (yes_ask.py). The outcome of a confirmed
  action's write is said at a turn boundary (action_job.py's `flush`).

Every event the talker gives is played as one step of the session's (`guarded`, under its lock,
in the order they came), so it never interleaves with one the Pipecat side hands; the client is
told what the agent is doing after each (`sync`). Each reply's run, what it keeps and lets out,
and its close are talk_runner.py's `TalkRunner`.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from t2_agentic_voice.agent.language import reply_language
from t2_agentic_voice.agent.talker import Talker, TalkerEvent
from t2_agentic_voice.core.conversation import TalkerTurn, heard_language
from t2_agentic_voice.core.events import TurnId
from t2_agentic_voice.core.yes_inputs import HeardWords
from t2_agentic_voice.voice.session.books import CallBooks
from t2_agentic_voice.voice.session.io import CallSetup, Guarded
from t2_agentic_voice.voice.session.kept_reply import KeptReplies
from t2_agentic_voice.voice.session.playback import Reply
from t2_agentic_voice.voice.session.read_back import Confirming
from t2_agentic_voice.voice.session.report import TurnLog
from t2_agentic_voice.voice.session.scope import CancelScope
from t2_agentic_voice.voice.session.speaker import Speaker
from t2_agentic_voice.voice.session.talk_runner import TalkRunner
from t2_agentic_voice.voice.session.talker_play import Talk, TalkPlayer
from t2_agentic_voice.voice.session.talker_progress import ProgressLines
from t2_agentic_voice.voice.session.turn_book import TurnBook
from t2_agentic_voice.voice.session.yes_turns import Receipt, YesTurns


class Talking(KeptReplies):
    """One call's talker replies, played by `speaker` for the turns `turns` keeps, each event
    played as a step `guarded` runs, the client's state brought up to date by `sync`; `over`
    says whether the call has ended or is ending."""

    def __init__(
        self,
        setup: CallSetup,
        books: CallBooks,
        *,
        talker: Talker,
        speaker: Speaker,
        turns: TurnBook,
        guarded: Guarded,
        sync: Callable[[], Awaitable[None]],
        over: Callable[[], bool],
        confirming: Confirming,
        receipt: Receipt,
    ) -> None:
        self._setup, self._speaker, self._turns = setup, speaker, turns
        self._events, self._history = books.events, books.history
        self._guarded, self._sync, self._over = guarded, sync, over
        self._clock, self._confirming = setup.clock, confirming
        self._over_reply = setup.settings.session.early_over_reply  # TD-117's early start
        self._player = TalkPlayer(setup, books.usage, turns, books.trace, confirming)
        self._progress = ProgressLines(setup, turns, self._player, guarded=guarded, sync=sync)
        self._runner = TalkRunner(
            setup,
            books,
            talker=talker,
            player=self._player,
            guarded=guarded,
            sync=sync,
            play=self._play,
        )
        self.yes = YesTurns(
            setup,
            books,
            speaker=speaker,
            turns=turns,
            confirming=confirming,
            receipt=receipt,
            talk=self.answer,
            guarded=guarded,
            sync=sync,
            over=over,
        )
        self._talks: dict[TurnId, Talk] = {}
        self._holding: set[TurnId] = set()  # the turns whose hold began and has not resumed
        self._open: set[TurnId] = set()  # the turns open, no overlap, not yet taken (kept replies)

    async def answer(self, turn: TurnLog, heard: HeardWords, at: float) -> None:
        """Answer `turn`, its words `heard`, with the talker, unless they answer an action's
        read-back (the yes rule's: yes_turns.py) or its early start answers it already (the same
        words); the replies in progress to earlier turns stopped first."""
        if self.yes.takes(heard, turn):
            await self.yes.answer(turn, heard, at)
            return
        talk = self._talks.get(turn.turn_id)
        if talk is not None and talk.reply is None and talk.scope.cancelled:  # stopped in the hold
            self._turns.ended(turn, "rolled_back")
            return
        if talk is not None and talk.early and talk.words == heard.text:
            if talk.reply is None:
                await self.release(turn, at)
            return
        if talk is not None:
            await self._dropped(talk)
            if talk.reply is not None:  # its reply said other words: stopped
                await self._speaker.stop(at, client=False)
        await self._stop_earlier(turn, at)
        handed = self._turn(turn, heard)
        reply = await self._speaker.open_reply(at, turn_id=turn.turn_id)
        turn.reply_id = reply.reply_id
        talk = Talk(turn_id=turn.turn_id, words=heard.text, scope=reply.scope, reply=reply)
        talk.kept_for = self._newer(turn.turn_id)
        self._start(talk, handed)

    async def hold(self, turn_id: TurnId, *, held: bool) -> None:
        """Smart Turn called the turn complete (`held`), so its `held` transcript may start the
        talker; or the caller spoke again within its hold, so what its early start began is
        cancelled, and the turn goes on (the module's early start)."""
        if held:
            self._holding.add(turn_id)
            return
        self._holding.discard(turn_id)
        talk = self._talks.get(turn_id)
        if talk is not None and talk.reply is None:
            await self._dropped(talk)

    async def held(self, turn: TurnLog, heard: HeardWords | None) -> None:
        """The turn's `held` transcript, its speech so far when its hold began, came while the
        hold runs: the talker starts on it, its events kept until the hold ends (the module's
        early start), for a turn said while the agent was silent, open, with words heard, that
        answers no read-back (the yes rule's: yes_turns.py), once the call goes on and no reply
        to an earlier turn is in progress, or one is, stopped first (`session.early_over_reply`)."""
        if heard is None or self._over() or turn.overlap or turn.dropped or turn.closed:
            return
        if self.yes.takes(heard, turn) or turn.turn_id not in self._holding:
            return
        if turn.turn_id in self._talks:
            return
        if self._earlier(turn.turn_id) is not None:
            if not self._over_reply or self._confirming.active:
                return
            await self._stop_earlier(turn, self._clock.now())
        scope = CancelScope(name=f"held-{turn.turn_id}", clock=self._clock)
        talk = Talk(turn_id=turn.turn_id, words=heard.text, scope=scope, early=True)
        self._start(talk, self._turn(turn, heard))

    async def release(self, turn: TurnLog, at: float) -> None:
        """The turn's hold ended (its `TurnClosed`): the reply its early start wrote is opened
        in its scope, what it kept played in order (unless a newer turn keeps it), and closed
        when its talker is done."""
        self._holding.discard(turn.turn_id)
        talk = self._talks.get(turn.turn_id)
        if talk is None or talk.reply is not None or talk.scope.cancelled:
            return
        if self._over():  # the call has ended, or its `ended` notice plays: nothing kept plays
            await self._dropped(talk)
            return
        await self._stop_earlier(turn, at)
        talk.kept_for = self._newer(turn.turn_id)
        talk.reply = await self._speaker.open_reply(at, turn_id=turn.turn_id, scope=talk.scope)
        turn.reply_id = talk.reply.reply_id
        if not talk.kept_for:
            await self._runner.let_out(talk)

    async def stopped(self) -> None:
        """The client's `stop`: the work of every early start still held is cancelled, so
        nothing it kept plays, and its turn is answered by nothing (`answer`)."""
        await self.yes.stopped()
        for talk in [talk for talk in self._talks.values() if talk.reply is None]:
            await self._runner.cancel(talk)

    async def end(self) -> None:
        """The call ended: every early start still held, and every kept reply, is cancelled (a
        reply's own scope is cancelled with the reply); an action's outcome due is never said."""
        await self.yes.end()
        self._open.clear()
        for talk in [talk for talk in self._talks.values() if talk.held]:
            talk.kept_for.clear()
            await self._dropped(talk)

    def _turn(self, turn: TurnLog, heard: HeardWords) -> TalkerTurn:
        """The turn as the talker reads it: its words whole, the language they were heard in,
        the language it asked for (call_language.py), the replies it spoke over and cut, the
        action it declined (read_back.py's `handed`), and the call before it as heard."""
        return TalkerTurn(
            turn_id=turn.turn_id,
            words=heard.text,
            language=heard_language(heard.language),
            asked=self._setup.now.asked_tag(heard.text),
            over_reply=turn.over_reply,
            cut_reply=turn.cut_reply,
            declined=self._confirming.handed(turn.turn_id, words=heard.text),
            conversation=self._history.conversation(before=turn.turn_id),
        )

    def _start(self, talk: Talk, turn: TalkerTurn) -> None:
        now = self._setup.now  # the call's current language, and the agent's (call_language.py)
        talk.language = reply_language(turn, call=now.tag, spoken=now.spoken)
        self._talks[talk.turn_id] = talk
        talk.scope.start(self._runner.run(talk, turn), name=f"talker-{talk.turn_id}")

    async def _dropped(self, talk: Talk) -> None:
        """`talk` is let go: its work cancelled (its reply, if opened, stopped by whoever
        dropped it)."""
        if self._talks.get(talk.turn_id) is talk:
            del self._talks[talk.turn_id]
        await self._runner.cancel(talk)

    async def _stop_earlier(self, turn: TurnLog, at: float) -> None:
        """Before `turn` is answered: the replies in progress to earlier turns stopped, their
        work cancelled, with one `Interrupted`; none when one answers this turn or a later
        one."""
        newest = self._earlier(turn.turn_id)
        if newest is None:
            return
        await self._speaker.stop(at, client=False)
        turn.cut_reply = turn.cut_reply if turn.cut_reply is not None else newest.reply_id
        self._events.interrupted(newest.turn_id, "new_words")

    def _earlier(self, turn_id: TurnId) -> Reply | None:
        """The newest reply in progress to an earlier turn (playback.py's `Playback.earlier`);
        None when there is none."""
        earlier = self._speaker.playback.earlier(turn_id)
        return earlier[-1] if earlier else None

    async def _play(self, talk: Talk, event: TalkerEvent, at: float) -> None:
        """Play one of the talker's events (talker_play.py), then tell the client what the agent
        is doing; a progress line with a time set is said at that time (talker_progress.py)."""
        if not self._progress.now(talk, event):
            return
        await self._player.play(talk, event, at)
        await self._sync()
