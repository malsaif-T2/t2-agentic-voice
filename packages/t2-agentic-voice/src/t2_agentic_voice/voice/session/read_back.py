"""An action's read-back in the session (the design's 6.4; docs/SECURITY.md, invariant 1): the
call's confirming state, and the only place a `ReadBackReceipt` is built, from the transport's
`ClausePlayed` reports, never the browser's `playback` message.

- **Confirming.** The talker's `ReadBackRequested` starts it when it plays (talker_play.py), never
  when it is written: the plan's summary, then its closing question, said as the reply's next
  clauses (`read`), each a template the output guard does not check (the design's 8.2), each
  clause marked with its part (playback.py's `ReadBackPart`). While it holds, the client is shown
  `confirming` whenever no reply plays (speaker.py's `show_state`). One read-back is current at a
  time: a new one, or the same one said again, takes the place of the last.
- **What is heard over it.** Yes words, send words, fillers and listening sounds whose speech
  began before the summary's last clause played are ignored (read_back_heard.py's `plays_on`):
  the summary plays on, and they count for nothing (overlap.py takes them as a listening
  sound). Words that hold a stop or pause word are never ignored, so khalas (enough), a stop
  word and a filler, stops it, but beside a yes word under `interruptions.yes_over_read_back`,
  which holds a yes over the summary (read_back_heard.py's `takes`, held_yes.py; D-108). A stop
  or pause word (the interruption rule's stop and wait words) over the read-back, or real words
  over its summary, stop it (`cut_by`): no receipt, the confirming state ends and nothing is
  sent; the turn reaches the talker, its stop word included, the action declined as `stopped`
  after a stop or pause word, as a `no` after words that are a plain no by the yes rule's
  lists, and as a `correction` after other real words (`handed`), so the talker answers in its
  own words, or asks what to change, its draft kept; and only a new read-back played in full
  can earn a yes.
  A turn begun in the gap before its first audio is no overlap, and the summary plays on over
  it; its words reaching the talker decline it as a `correction` (or a `no`) all the same
  (`handed`). A repeat request over it, or said whole while it is confirming, has the session
  say it again (`again`; read_back_moved.py's `read_again`), the earlier one void. Other words
  over the closing question are the yes rule's. The client's `stop` while it plays, its reply
  ending before its summary played whole, and the call's end end it too.
- **The receipt** (`receipt`), built only when the yes rule is called: what it stands for, and
  when each part of the read-back played or could first be heard, are read_back_times.py's.
- **The answer** (yes_turns.py). A turn whose speech began once the summary's last clause played
  answers it (`answering`) and goes to the yes rule with its words (`words`): a yes ends
  confirming (`confirmed`); a no or a correction too, the turn reaching the talker with the
  action declined so (`decline`); an unclear answer is asked again (`asks_again`) at most the
  plan's `max_attempts` times, each line a follow-up of the read-back (`follow_up`), over which a
  stop or pause word or a repeat request does as over the read-back; after the last, confirming
  ends. A stop or pause request said whole while confirming is a stop word over it (the owner's
  ruling). Each read-back's first audio is the public `ConfirmationRequested` (`queued`); which
  turns declined it, and how, are read_back_declines.py's.
- **The flow.** Each read-back's action moves through domain/action_flow.py's table as
  confirming ends or goes on (`state`; read_back_flow.py), a move it refuses logged, never raised.
- **What was still heard** (D-082's echo rail; `over_read_back`, `over_follow_up`, and whether
  speech answers it, `answering`) is read_back_times.py's `ReadBackTimes`.
"""

from __future__ import annotations

from t2_agentic_voice.core.conversation import DeclinedAction, DeclineKind
from t2_agentic_voice.core.events import ConfirmationRequested, ReplyId, TurnId
from t2_agentic_voice.core.yes_inputs import READ_BACK_SEAL, ReadBackReceipt
from t2_agentic_voice.domain.action_flow import ActionState
from t2_agentic_voice.domain.action_lines import ReadBackPlan
from t2_agentic_voice.domain.interruptions import Verdict
from t2_agentic_voice.domain.yes_words import ConsentWords, consent_words
from t2_agentic_voice.voice.protocol import ClauseIndex
from t2_agentic_voice.voice.session import read_back_times as times
from t2_agentic_voice.voice.session.io import CallSetup
from t2_agentic_voice.voice.session.open_reply import OpenReply, language_of
from t2_agentic_voice.voice.session.playback import Playback, Reply
from t2_agentic_voice.voice.session.read_back_declines import Declines
from t2_agentic_voice.voice.session.read_back_flow import ReadBackFlow
from t2_agentic_voice.voice.session.read_back_times import ReadBack, ReadBackTimes, Undecided


def played_receipt(
    *,
    action: str,
    draft_json: str,
    reply_id: ReplyId,
    summary_played_at: float,
    question_ended_at: float | None,
    summary_began_at: float | None = None,
) -> ReadBackReceipt:
    """The receipt of `action`'s read-back of `draft_json` in reply `reply_id`. The caller has
    checked everything read_back_times.py's docstring says; this only builds it."""
    values = {
        "action": action,
        "draft_json": draft_json,
        "reply_id": reply_id,
        "summary_played_at": summary_played_at,
        "question_ended_at": question_ended_at,
        "summary_began_at": summary_began_at,
    }
    return ReadBackReceipt.model_validate(values, context=READ_BACK_SEAL)


class Confirming(ReadBackTimes):
    """One call's confirming state (the module's docstring), over the replies `playback` keeps,
    in the call `setup` gives."""

    def __init__(self, setup: CallSetup, playback: Playback) -> None:
        self._setup, self._playback = setup, playback
        self.read_back: ReadBack | None = None  # the current read-back; None when not confirming
        self._flow, self._declines = ReadBackFlow(setup.call_id), Declines()
        self._asked = 0  # how many times the current read-back was asked again
        self._follow_ups: set[ReplyId] = set()  # the lines that asked it again
        self.holds_yes = setup.settings.interruptions.yes_over_read_back  # D-108, off by default
        self.asks = setup.agent.ask_on_unlisted_answers and setup.overlap_model is not None

    @property
    def state(self) -> ActionState | None:
        """The current or last read-back's action, as the table moved it (the module's flow)."""
        return self._flow.state

    @property
    def active(self) -> bool:
        """Whether a read-back is current: the call is confirming."""
        return self.read_back is not None

    async def read(self, reply: OpenReply, plan: ReadBackPlan, at: float) -> ReadBack | None:
        """Say `plan`'s summary, then its closing question, as the next clauses of `reply`, in
        the plan's language, at `at`: the current read-back, in place of any before it, never
        yet asked again; None, confirming nothing, when the reply was dropped before both were
        asked for."""
        self.read_back, self._asked = None, 0
        self._follow_ups.clear()
        tag = plan.language
        summary = await reply.add_line(plan.summary, language=tag, at=at, part="summary")
        if not summary:
            return None
        question = await reply.add_line(plan.question, language=tag, at=at, part="question")
        if not question:
            return None
        read_back = ReadBack(plan=plan, reply_id=reply.reply_id, summary=summary, question=question)
        self.read_back = read_back
        self._flow.began(plan.action)
        return read_back

    def queued(self, reply: Reply, index: ClauseIndex) -> None:
        """Clause `index` of `reply` began to play (its first audio queued): the public
        `ConfirmationRequested`, when it is the current read-back's first."""
        read_back = self.read_back
        if read_back is None or reply.reply_id != read_back.reply_id or reply.turn_id is None:
            return
        if index == read_back.summary[0]:
            wall, call_id = self._setup.clock.wall(), self._setup.call_id
            plan = read_back.plan
            began = ConfirmationRequested(
                call_id=call_id,
                turn_id=reply.turn_id,
                at=wall,
                action=plan.action,
                draft=plan.draft_json,
            )
            self._setup.emit(began)

    def words(self, plan: ReadBackPlan) -> ConsentWords:
        """The yes rule's words for `plan`'s read-back, in its language: the preset's, the
        `words` settings group's additions and the action's own send words."""
        code = language_of(self._setup, plan.language).primary
        added = self._setup.settings.words
        return consent_words(
            code,
            added_yes=added.yes.get(code, ()),
            added_send=added.send.get(code, ()),
            action_send=plan.send_words,
        )

    def decline(self, turn_id: TurnId, kind: DeclineKind) -> None:
        """The caller's turn `turn_id` declined the current read-back, as `kind`: confirming
        ends, and the turn reaches the talker with the action declined so (`handed`)."""
        read_back = self.read_back
        if read_back is not None:
            self._declines.add(turn_id, read_back.plan, kind)
            self.read_back = None
            self._flow.declined(kind)

    def confirmed(self) -> None:
        """The yes rule issued a yes: confirming ends, the action `confirmed`."""
        self._flow.move("yes")
        self.finish()

    def finish(self) -> None:
        """Confirming ends: a yes, no clear answer after the last ask-again, the client's stop
        or the call's end."""
        self.read_back = None
        self._follow_ups.clear()

    def asks_again(self) -> bool:
        """The caller's answer to the current read-back was unclear: whether it is asked again,
        at most its plan's `max_attempts` times; after that, confirming ends (`finish`)."""
        read_back = self.read_back
        if read_back is None:
            return False
        self._asked += 1
        if self._asked <= read_back.plan.max_attempts:
            self._flow.move("asked_again")
            return True
        self._flow.move("unclear")
        self.finish()
        return False

    def follow_up(self, reply_id: ReplyId) -> None:
        """Reply `reply_id` asked the current read-back again: what is said over it is taken as
        over the closing question (`cut_by`, `stopped`)."""
        if self.read_back is not None:
            self._follow_ups.add(reply_id)

    def cut_by(
        self, turn_id: TurnId, *, reply_id: ReplyId, speech_at: float, verdict: Verdict
    ) -> None:
        """An overlap of the caller's turn `turn_id`, begun over reply `reply_id` at `speech_at`,
        stops the agent for `verdict`: over the current read-back or a line that asked it again,
        a repeat request has it said again (`again`), a stop or pause word declines it as
        stopped, and real words over its summary as a correction, or a no when the turn's words
        are a plain no (`handed`), the turn's words going to the talker; either ends it. Real
        words over the closing question, or over a line that asked it again, leave it to the
        yes rule."""
        read_back = self.read_back
        if read_back is None or verdict.action == "go_on":
            return
        if reply_id != read_back.reply_id and reply_id not in self._follow_ups:
            return
        if verdict.action == "repeat":  # moved once said again, or answered instead
            self._declines.repeat(turn_id, read_back.plan)
            self.read_back = None
            return
        summary = self._playback.reply(read_back.reply_id), read_back.summary
        if verdict.kind != "stop" and not times.over(*summary, speech_at):
            return
        self.decline(turn_id, "stopped" if verdict.kind == "stop" else "correction")

    def again(self, turn_id: TurnId) -> ReadBackPlan | None:
        """The read-back the caller's turn `turn_id` asked to hear again, to say now, its
        action no longer declined by it; None when it asked for none."""
        return self._declines.again(turn_id)

    def repeated(self) -> None:
        """The caller asked to hear the read-back again, and it is said again now (`read`)."""
        self._flow.move("repeat")

    def declines(self, turn_id: TurnId) -> bool:
        """Whether the caller's turn `turn_id` stopped a read-back."""
        return self._declines.holds(turn_id)

    def handed(self, turn_id: TurnId, *, words: str) -> DeclinedAction | None:
        """The action the caller's turn `turn_id`, its words `words`, declined, as the talker
        learns of it: a `no`, a `correction`, or `stopped` (a stop or pause word), so it
        answers in its own words; None when the turn declined none. A turn handed to the talker
        while a read-back is current began before its summary ended, or has no time (in the gap
        before its first audio, the summary playing on over it), so it declines it first, as a
        correction: confirming ends, and no later yes confirms a draft the caller spoke over; so
        does a repeat request answered instead of said again. A correction whose words are a
        plain no is told as a `no` (read_back_declines.py's `told`)."""
        if not self._declines.holds(turn_id):
            self.decline(turn_id, "correction")
        elif self._declines.answered(turn_id):
            self._flow.move("correction")
        return self._declines.told(turn_id, words=words, consent=self.words)

    def stopped(self) -> None:
        """The client's `stop`: a read-back, or a line that asked it again, still playing
        ends, with no receipt."""
        read_back = self.read_back
        if read_back is None:
            return
        for reply_id in (read_back.reply_id, *self._follow_ups):
            reply = self._playback.reply(reply_id)
            if reply is not None and reply.ended_at is None:
                self.finish()
                return

    def reply_ended(self, reply: Reply) -> None:
        """`reply` ended, however: when it says the current read-back and its summary did not
        play whole (a stop or the call's end cut it, a clause failed), confirming ends."""
        read_back = self.read_back
        if read_back is None or reply.reply_id != read_back.reply_id:
            return
        if times.whole(reply, read_back.summary) is None:
            self.read_back = None

    def end(self) -> None:
        """The call ended: confirming ends, and nothing is said again."""
        self.finish()
        self._declines.end()

    def receipt(self, *, speech_at: float | None, undecided: Undecided) -> ReadBackReceipt | None:
        """The current read-back's receipt for a turn whose speech began at `speech_at`, built
        now (read_back_times.py's docstring); None while any of it does not hold, or no
        read-back is current."""
        read_back = self.read_back
        if read_back is None or speech_at is None:
            return None
        reply = self._playback.reply(read_back.reply_id)
        summary_at = times.whole(reply, read_back.summary)
        if summary_at is None or speech_at < summary_at:
            return None
        if undecided(read_back.reply_id, summary_at):
            return None
        return played_receipt(
            action=read_back.plan.action,
            draft_json=read_back.plan.draft_json,
            reply_id=read_back.reply_id,
            summary_played_at=summary_at,
            question_ended_at=times.whole(reply, read_back.question),
            summary_began_at=times.began(reply, read_back.summary),
        )
