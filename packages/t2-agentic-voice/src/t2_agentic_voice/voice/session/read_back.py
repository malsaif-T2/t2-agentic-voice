"""An action's read-back in the session (plan 007; the design's 6.4; docs/SECURITY.md, invariant
1): the call's confirming state, and the only place a `ReadBackReceipt` is built, from the
transport's `ClausePlayed` reports, never the browser's `playback` message.

- **Confirming.** The talker's `ReadBackRequested` starts it when it plays (talker_play.py), never
  when it is written: the plan's summary, then its closing question, said as the reply's next
  clauses (`read`), each a template the output guard does not check (the design's 8.2), each
  clause marked with its part (playback.py's `ReadBackPart`). While it holds, the client is shown
  `confirming` whenever no reply plays (speaker.py's `show_state`). One read-back is current at a
  time: a new one, or the same one said again, takes the place of the last.
- **What is heard over it.** Yes words, send words, fillers and listening sounds whose speech
  began before the summary's last clause played are ignored (`ignored`): the summary plays on,
  and they count for nothing (overlap.py takes them as a listening sound). A stop or pause word
  (the interruption rule's stop and wait words) over the read-back, or real words over its
  summary, stop it (`cut_by`): no receipt, the confirming state ends and nothing is sent; the
  turn reaches the talker, its stop word included, the action declined as a correction
  (`declined`), so the talker asks what to change in its own words, its draft kept; and only a
  new read-back played in full can earn a yes. A repeat request over it, or said whole while it
  is confirming, has the session say it again (`again`, `read_again`), the earlier one void.
  Other words over the closing question are the yes rule's. The client's `stop` while it plays,
  its reply ending before its summary played whole, and the call's end end it too.
- **The receipt** (`receipt`), built only when the yes rule is called, so a verdict landing late
  can still deny it: it stands for a summary that played whole, every clause of it played, none
  cut short, each with audio (a stop that cut the reply after its summary changes none of that);
  no overlap begun over the summary undecided; and the turn's speech begun once its last clause
  played. Its `question_ended_at` is the closing question's last `ClausePlayed`, None until every
  clause of the question has played so.
"""

from __future__ import annotations

from collections.abc import Callable, Collection
from dataclasses import dataclass

from t2_agentic_voice.core.conversation import DeclinedAction
from t2_agentic_voice.core.events import ReplyId, TurnId
from t2_agentic_voice.core.yes_inputs import READ_BACK_SEAL, ReadBackReceipt
from t2_agentic_voice.domain.action_lines import ReadBackPlan
from t2_agentic_voice.domain.interruptions import Verdict
from t2_agentic_voice.domain.words import rule_form
from t2_agentic_voice.domain.yes_words import consent_words
from t2_agentic_voice.voice.protocol import ClauseIndex
from t2_agentic_voice.voice.session.io import CallSetup
from t2_agentic_voice.voice.session.open_reply import OpenReply, language_of
from t2_agentic_voice.voice.session.playback import Playback, Reply
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


def _covered(text: str, phrases: Collection[str]) -> bool:
    """Whether every word of `text` belongs to one of `phrases`, both in the rule's form
    (domain/words.py's `rule_form`), each phrase whole words, the longest first; False for a
    text with no word."""
    heard = rule_form(text).split()
    forms = {form for form in (rule_form(phrase) for phrase in phrases) if form}
    if not heard or not forms:
        return False
    longest = max(len(form.split()) for form in forms)
    at = 0
    while at < len(heard):
        sizes = range(min(longest, len(heard) - at), 0, -1)
        size = next((n for n in sizes if " ".join(heard[at : at + n]) in forms), 0)
        if not size:
            return False
        at += size
    return True


class Confirming:
    """One call's confirming state (the module's docstring), over the replies `playback` keeps,
    in the call `setup` gives."""

    def __init__(self, setup: CallSetup, playback: Playback) -> None:
        self._setup, self._playback = setup, playback
        self.read_back: ReadBack | None = None  # the current read-back; None when not confirming
        self._declined: dict[TurnId, str] = {}  # each turn that stopped a read-back: its action
        self._again: dict[TurnId, ReadBackPlan] = {}  # each turn whose repeat request said again

    @property
    def active(self) -> bool:
        """Whether a read-back is current: the call is confirming."""
        return self.read_back is not None

    async def read(self, reply: OpenReply, plan: ReadBackPlan, at: float) -> ReadBack | None:
        """Say `plan`'s summary, then its closing question, as the next clauses of `reply`, in
        the plan's language, at `at`: the current read-back, in place of any before it; None,
        confirming nothing, when the reply was dropped before both were asked for."""
        self.read_back = None
        tag = plan.language
        summary = await reply.add_line(plan.summary, language=tag, at=at, part="summary")
        if not summary:
            return None
        question = await reply.add_line(plan.question, language=tag, at=at, part="question")
        if not question:
            return None
        read_back = ReadBack(plan=plan, reply_id=reply.reply_id, summary=summary, question=question)
        self.read_back = read_back
        return read_back

    def ignored(
        self, reply_id: ReplyId, speech_at: float, text: str, *, listening: Collection[str]
    ) -> bool:
        """Whether `text`, said over reply `reply_id` from `speech_at`, is yes words, send words,
        fillers and `listening` sounds only, begun over the current read-back's summary: ignored,
        the summary playing on."""
        read_back = self.read_back
        if read_back is None or reply_id != read_back.reply_id:
            return False
        if not self._over_summary(read_back, speech_at):
            return False
        plan, code = read_back.plan, language_of(self._setup, read_back.plan.language).primary
        added = self._setup.settings.words
        words = consent_words(
            code,
            added_yes=added.yes.get(code, ()),
            added_send=added.send.get(code, ()),
            action_send=plan.send_words,
        )
        return _covered(text, (*words.yes, *words.send, *words.fillers, *listening))

    def cut_by(
        self, turn_id: TurnId, *, reply_id: ReplyId, speech_at: float, verdict: Verdict
    ) -> None:
        """An overlap of the caller's turn `turn_id`, begun over reply `reply_id` at `speech_at`,
        stops the agent for `verdict`: over the current read-back, a repeat request has it said
        again (`again`), and a stop or pause word, or real words over its summary, declines it
        (`declined`), the turn's words going to the talker; either ends it. Real words over the
        closing question leave it to the yes rule."""
        read_back = self.read_back
        if read_back is None or reply_id != read_back.reply_id or verdict.action == "go_on":
            return
        if verdict.action == "repeat":
            self._again[turn_id] = read_back.plan
        elif verdict.kind != "stop" and not self._over_summary(read_back, speech_at):
            return
        self._declined[turn_id] = read_back.plan.action
        self.read_back = None

    def again(self, turn_id: TurnId) -> ReadBackPlan | None:
        """The read-back the caller's turn `turn_id` asked to hear again, to say now, its
        action no longer declined by it; None when it asked for none."""
        plan = self._again.pop(turn_id, None)
        if plan is not None:
            self._declined.pop(turn_id, None)
        return plan

    def declines(self, turn_id: TurnId) -> bool:
        """Whether the caller's turn `turn_id` stopped a read-back."""
        return turn_id in self._declined

    def declined(self, turn_id: TurnId, *, words: str) -> DeclinedAction | None:
        """The action the caller's turn `turn_id`, its words `words`, declined by stopping its
        read-back, as the talker learns of it: a correction, so it asks what to change; None
        when the turn stopped none."""
        action = self._declined.get(turn_id)
        if action is None:
            return None
        return DeclinedAction(action=action, kind="correction", words=words)

    def stopped(self) -> None:
        """The client's `stop`: a read-back still playing ends, with no receipt."""
        read_back = self.read_back
        reply = None if read_back is None else self._playback.reply(read_back.reply_id)
        if reply is not None and reply.ended_at is None:
            self.read_back = None

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
        self.read_back = None
        self._again.clear()

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
    reply = await speaker.open_reply(at, turn_id=turn_id)
    await confirming.read(reply, plan, at)
    await reply.finish(at)
    return reply.reply_id
