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
  began before the summary's last clause played are ignored (`ignored`): the summary plays on,
  and they count for nothing (overlap.py takes them as a listening sound). Words that hold a
  stop or pause word are never ignored (overlap.py reads them first), so khalas (enough), a
  stop word and a filler, stops it. A stop or pause word (the interruption rule's stop and wait
  words) over the read-back, or real words over its summary, stop it (`cut_by`): no receipt,
  the confirming state ends and nothing is sent; the turn reaches the talker, its stop word
  included, the action declined as `stopped` after a stop or pause word, as a `no` after words
  that are a plain no by the yes rule's lists, and as a `correction` after other real words
  (`handed`), so the talker answers in its own words, or asks what to change, its draft kept;
  and only a new read-back played in full can earn a yes. A turn begun in the gap before its
  first audio is no overlap, and the summary plays on over it; its words reaching the talker
  decline it as a `correction` (or a `no`) all the same (`handed`). A repeat request over it, or
  said whole while it is confirming, has the session say it again (`again`, `read_again`), the
  earlier one void. Other words over the closing question are the yes rule's. The client's
  `stop` while it plays, its reply ending before its summary played whole, and the call's end
  end it too.
- **The receipt** (`receipt`), built only when the yes rule is called, so a verdict landing late
  can still deny it: it stands for a summary that played whole, every clause of it played, none
  cut short, each with audio (a stop that cut the reply after its summary changes none of that);
  no overlap begun over the summary undecided; and the turn's speech begun once its last clause
  played. Its `question_ended_at` is the closing question's last `ClausePlayed`, None until every
  clause of the question has played so.
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
- **What was still heard** (D-082's echo rail). Whether a turn's speech began while the
  read-back, or a line that asked it again, was still heard (`over_read_back`,
  `over_follow_up`): its reply playing, or within its tail after it ended, the drop rule's
  window (playback.py's `Reply.over`); True when the session cannot tell.
"""

from __future__ import annotations

from collections.abc import Callable, Collection
from dataclasses import dataclass

from t2_agentic_voice.core.conversation import DeclinedAction, DeclineKind
from t2_agentic_voice.core.events import ConfirmationRequested, ReplyId, TurnId
from t2_agentic_voice.core.yes_inputs import READ_BACK_SEAL, ReadBackReceipt
from t2_agentic_voice.domain.action_flow import ActionState
from t2_agentic_voice.domain.action_lines import ReadBackPlan
from t2_agentic_voice.domain.interruptions import Verdict
from t2_agentic_voice.domain.yes_words import ConsentWords, consent_words, covered
from t2_agentic_voice.voice.protocol import ClauseIndex
from t2_agentic_voice.voice.session.io import CallSetup
from t2_agentic_voice.voice.session.open_reply import OpenReply, language_of
from t2_agentic_voice.voice.session.playback import Playback, Reply
from t2_agentic_voice.voice.session.read_back_declines import Declines
from t2_agentic_voice.voice.session.read_back_flow import ReadBackFlow
from t2_agentic_voice.voice.session.speaker import Speaker

# Whether an overlap of a reply, its speech begun before a time, is still undecided (overlap.py's
# `Overlaps.undecided`).
Undecided = Callable[[ReplyId, float], bool]


def played_receipt(
    *,
    action: str,
    draft_json: str,
    reply_id: ReplyId,
    summary_played_at: float,
    question_ended_at: float | None,
) -> ReadBackReceipt:
    """The receipt of `action`'s read-back of `draft_json` in reply `reply_id`. The caller has
    checked everything the module's docstring says; this only builds it."""
    values = {
        "action": action,
        "draft_json": draft_json,
        "reply_id": reply_id,
        "summary_played_at": summary_played_at,
        "question_ended_at": question_ended_at,
    }
    return ReadBackReceipt.model_validate(values, context=READ_BACK_SEAL)


@dataclass(frozen=True, kw_only=True)
class ReadBack:
    """One draft read back: its `plan`, the reply that says it, and the indexes of its clauses
    there, the summary's and the closing question's."""

    plan: ReadBackPlan
    reply_id: ReplyId
    summary: tuple[ClauseIndex, ...]
    question: tuple[ClauseIndex, ...]


class Confirming:
    """One call's confirming state (the module's docstring), over the replies `playback` keeps,
    in the call `setup` gives."""

    def __init__(self, setup: CallSetup, playback: Playback) -> None:
        self._setup, self._playback = setup, playback
        self.read_back: ReadBack | None = None  # the current read-back; None when not confirming
        self._flow, self._declines = ReadBackFlow(setup.call_id), Declines()
        self._asked = 0  # how many times the current read-back was asked again
        self._follow_ups: set[ReplyId] = set()  # the lines that asked it again

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

    def answering(self, speech_at: float | None) -> bool:
        """Whether speech begun at `speech_at` answers the current read-back: it began once
        the read-back's summary had played its last clause (yes_turns.py's)."""
        read_back = self.read_back
        if read_back is None or speech_at is None:
            return False
        return not self._over_summary(read_back, speech_at)

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

    def over_read_back(self, speech_at: float | None) -> bool:
        """Whether speech begun at `speech_at` began while the current read-back was still
        heard: its reply playing, or within its tail after it ended (playback.py's
        `Reply.over`, the drop rule's window, the transport's reports); True when the session
        cannot tell, so the yes rule's echo rail keeps its lines (domain/yes_rule.py's
        `judged`)."""
        read_back = self.read_back
        return read_back is None or self._heard(speech_at, (read_back.reply_id,))

    def over_follow_up(self, speech_at: float | None) -> bool:
        """Whether speech begun at `speech_at` began while a line that asked the current
        read-back again was still heard: from its reply's first audio queued to the end of its
        tail after it ended, as `over_read_back` reads the read-back's; True when the session
        cannot tell, so the echo rail keeps that line."""
        return self._heard(speech_at, self._follow_ups)

    def _heard(self, speech_at: float | None, reply_ids: Collection[ReplyId]) -> bool:
        """Whether speech begun at `speech_at` began over one of `reply_ids`, its tail included;
        True with no time, or for a reply the session no longer holds."""
        if speech_at is None:
            return True
        for reply_id in reply_ids:
            reply = self._playback.reply(reply_id)
            if reply is None or reply.over(speech_at):
                return True
        return False

    def ignored(
        self, reply_id: ReplyId, speech_at: float, text: str, *, listening: Collection[str]
    ) -> bool:
        """Whether `text`, said over reply `reply_id` from `speech_at`, is yes words, send words,
        fillers and `listening` sounds only, begun over the current read-back's summary: ignored,
        the summary playing on. Never asked of words with a stop or pause word (overlap.py)."""
        read_back = self.read_back
        if read_back is None or reply_id != read_back.reply_id:
            return False
        if not self._over_summary(read_back, speech_at):
            return False
        words = self.words(read_back.plan)
        return covered(text, (*words.yes, *words.send, *words.fillers, *listening))

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
        if verdict.kind != "stop" and not self._over_summary(read_back, speech_at):
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
        if self._whole(read_back, read_back.summary) is None:
            self.read_back = None

    def end(self) -> None:
        """The call ended: confirming ends, and nothing is said again."""
        self.finish()
        self._declines.end()

    def receipt(self, *, speech_at: float | None, undecided: Undecided) -> ReadBackReceipt | None:
        """The current read-back's receipt for a turn whose speech began at `speech_at`, built
        now (the module's docstring); None while any of it does not hold, or no read-back is
        current."""
        read_back = self.read_back
        if read_back is None or speech_at is None:
            return None
        summary_at = self._whole(read_back, read_back.summary)
        if summary_at is None or speech_at < summary_at:
            return None
        if undecided(read_back.reply_id, summary_at):
            return None
        return played_receipt(
            action=read_back.plan.action,
            draft_json=read_back.plan.draft_json,
            reply_id=read_back.reply_id,
            summary_played_at=summary_at,
            question_ended_at=self._whole(read_back, read_back.question),
        )

    def _whole(self, read_back: ReadBack, indexes: tuple[ClauseIndex, ...]) -> float | None:
        """When the last of `indexes`, clauses of the read-back's reply, played, once every one
        of them played whole with audio; None until then, or when one never will."""
        reply = self._playback.reply(read_back.reply_id)
        if reply is None or not indexes:
            return None
        clauses = [reply.clauses[index] for index in indexes if index < len(reply.clauses)]
        if len(clauses) != len(indexes):
            return None
        if not all(c.played and not c.cut_short and c.audio_s > 0 for c in clauses):
            return None
        return max(c.played_at or 0.0 for c in clauses)

    def _over_summary(self, read_back: ReadBack, speech_at: float) -> bool:
        """Whether speech begun at `speech_at` began before the read-back's summary had played
        its last clause."""
        reply = self._playback.reply(read_back.reply_id)
        last = None if reply is None else reply.clauses[read_back.summary[-1]]
        ended = None if last is None or not last.played else last.played_at
        return ended is None or speech_at < ended


async def read_again(
    speaker: Speaker, confirming: Confirming, plan: ReadBackPlan, *, turn_id: TurnId, at: float
) -> ReplyId:
    """Say `plan`'s read-back again, at the caller's request, as a reply of its own answering
    `turn_id`, written whole at once: the current read-back, the earlier one void; its reply's
    number."""
    confirming.repeated()
    reply = await speaker.open_reply(at, turn_id=turn_id)
    await confirming.read(reply, plan, at)
    await reply.finish(at)
    return reply.reply_id
