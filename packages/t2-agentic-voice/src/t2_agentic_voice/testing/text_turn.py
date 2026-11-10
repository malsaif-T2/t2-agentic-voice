"""One turn of a `TextCall` and what came of it (testing/text_call.py; plans 006 and 007): its
checks (`TurnExpectations`, an action's among them: testing/text_actions.py) and what it did as
data (`TextTurn`, testing/turn_data.py's shapes), each read from the call as it now stands
(testing/text_reads.py): the session's heard history and its replies, the commands it gave (each
clause's language, and whether it was a fixed phrase), and what the call watched of its talker,
its tools and the part that acts (testing/text_watch.py). Every time is in seconds on the call's
clock, from the moment the turn's words were handed to the session.
"""

from __future__ import annotations

from pydantic import JsonValue

from t2_agentic_voice.agent.talker import (
    ClauseBlocked,
    ModelReplied,
    ModelRequested,
    ShownCard,
    SpokenClause,
    ToolBegan,
    ToolEnded,
)
from t2_agentic_voice.core.conversation import TurnFate
from t2_agentic_voice.core.settings.tts import LanguageTag
from t2_agentic_voice.domain.cards import Card
from t2_agentic_voice.domain.ports.action_jobs import OutcomeKind
from t2_agentic_voice.domain.ports.chat_model import Usage
from t2_agentic_voice.testing import text_actions
from t2_agentic_voice.testing.text_reads import TextReads
from t2_agentic_voice.testing.text_watch import TurnTalk, arguments_of
from t2_agentic_voice.testing.turn_data import (
    BlockedClause,
    HeardClause,
    TextToolCall,
    ToolOutcome,
)


class TextTurn:
    """One of the caller's turns in a `TextCall`, and what came of it: the checks (`expect`),
    and what it did as data (the module's docstring). Each read gives what the turn has done so
    far: a reply a later turn cuts, or a tool still running, reads as it now stands."""

    def __init__(self, _reads: TextReads, _turn_id: int) -> None:
        # Built by the text call alone, its reads internal (D-032: no public signature names
        # an internal type), so its parameters are private.
        self._reads, self.turn_id = _reads, _turn_id

    @property
    def expect(self) -> TurnExpectations:
        """The checks of what the turn did."""
        return TurnExpectations(self)

    @property
    def fate(self) -> TurnFate:
        """What became of the turn (core/conversation.py's `TurnFate`)."""
        turns = self._reads.session.history.turns()
        return next((t.fate for t in turns if t.turn_id == self.turn_id), "pending")

    @property
    def clauses(self) -> tuple[HeardClause, ...]:
        """The clauses of the turn's reply as the caller heard them, in order, fixed phrases
        among them; a clause the guard blocked is never one."""
        session, side = self._reads.session, self._reads.side
        found = []
        for reply in session.history.replies():
            if reply.turn_id != self.turn_id:
                continue
            for index, clause in enumerate(reply.clauses):
                speak = side.speaks.get((reply.reply_id, index))
                language = session.setup.language.tag if speak is None else speak.language
                found.append(
                    HeardClause(
                        text=clause.text,
                        language=language,
                        fate=clause.fate,
                        played_fraction=clause.played_fraction,
                        phrase=speak is not None and speak.audio is not None,
                    )
                )
        return tuple(found)

    def heard(self) -> tuple[HeardClause, ...]:
        """The clauses the caller heard, or is still to hear when no stop or end cut the reply:
        those played or cut, and those still to play of a reply not cut."""
        playback = self._reads.session.playback
        cut = any(
            reply.cut
            for reply in (playback.reply(i) for i in range(playback.next_id))
            if reply is not None and reply.turn_id == self.turn_id
        )
        return tuple(c for c in self.clauses if c.fate != "unplayed" or not cut)

    @property
    def _talk(self) -> TurnTalk | None:
        watched = self._reads.watched
        return None if watched is None else watched.talks.get(self.turn_id)

    @property
    def tool_calls(self) -> tuple[TextToolCall, ...]:
        """The tool calls the turn's reply made, in the order they began, each with when it
        began."""
        talk = self._talk
        if talk is None:
            return ()
        ended = {e.call_id: e for _, e in talk.events if isinstance(e, ToolEnded)}
        runner = self._reads.runner
        found = []
        for began_at, began in [(at, e) for at, e in talk.events if isinstance(e, ToolBegan)]:
            ran = None if runner is None else runner.calls.get(began.call_id)
            arguments: dict[str, JsonValue] = {} if ran is None else arguments_of(ran[0])
            end = ended.get(began.call_id)
            outcome: ToolOutcome
            ms: float | None = None
            stopped_at = self._stopped_at(talk)
            if end is not None:
                outcome, ms = ("ok" if end.ok else "failed"), end.ms
            elif stopped_at is not None:  # cancelled with its reply: timed to the reply's end
                outcome, ms = "cancelled", max(0.0, stopped_at - began_at) * 1000
            else:
                outcome = "running"
            found.append(
                TextToolCall(
                    call_id=began.call_id,
                    tool=began.tool,
                    arguments=arguments,
                    outcome=outcome,
                    ms=ms,
                    began_s=self._since(began_at),
                )
            )
        return tuple(found)

    def _stopped_at(self, talk: TurnTalk) -> float | None:
        """When the turn's reply was stopped or cut, its work cancelled with it; when its work
        was cancelled with no reply cut (its early start's), its last event's time; None while
        it runs."""
        playback = self._reads.session.playback
        replies = (playback.reply(i) for i in range(playback.next_id))
        cut = [r.ended_at for r in replies if r is not None and r.turn_id == self.turn_id and r.cut]
        if cut and cut[-1] is not None:
            return cut[-1]
        if talk.cancelled:
            return talk.events[-1][0] if talk.events else talk.began_at
        return None

    @property
    def cards(self) -> tuple[Card, ...]:
        """The cards the turn's reply showed, in order."""
        talk = self._talk
        return (
            ()
            if talk is None
            else tuple(e.card for _, e in talk.events if isinstance(e, ShownCard))
        )

    @property
    def blocked(self) -> tuple[BlockedClause, ...]:
        """The clauses of the turn's reply the output guard blocked, in order."""
        talk = self._talk
        if talk is None:
            return ()
        return tuple(
            BlockedClause(text=e.text, language=e.language, unsupported=e.unsupported)
            for _, e in talk.events
            if isinstance(e, ClauseBlocked)
        )

    def _since(self, at: float | None) -> float | None:
        said = self._reads.said.get(self.turn_id)
        return None if at is None or said is None else max(0.0, at - said.handed_at)

    @property
    def first_token_s(self) -> float | None:
        """The time to the first token of the turn's first model request, None when none
        came."""
        talk, asked = self._talk, None
        for at, event in [] if talk is None else talk.events:
            if isinstance(event, ModelRequested) and asked is None:
                asked = at
            elif isinstance(event, ModelReplied) and asked is not None:
                first = event.first_token_s
                return None if first is None else self._since(asked + first)
        return None

    @property
    def first_clause_s(self) -> float | None:
        """The time to the reply's first clause given to speak (from the caller's request to
        the talker's first words, a fixed phrase not counted), None when none was."""
        talk = self._talk
        spoken = [
            at for at, e in ([] if talk is None else talk.events) if isinstance(e, SpokenClause)
        ]
        return self._since(spoken[0]) if spoken else None

    @property
    def model_requests(self) -> int:
        """The model requests the turn's reply sent, each counted, answered or not."""
        talk = self._talk
        return 0 if talk is None else sum(isinstance(e, ModelRequested) for _, e in talk.events)

    @property
    def usage(self) -> Usage:
        """What the turn's model requests used, summed over those whose provider reported it
        (no tokens when none did)."""
        talk = self._talk
        used = [
            e.usage
            for _, e in ([] if talk is None else talk.events)
            if isinstance(e, ModelReplied) and e.usage is not None
        ]
        return Usage(
            input_tokens=sum(u.input_tokens for u in used),
            output_tokens=sum(u.output_tokens for u in used),
            cached_tokens=sum(u.cached_tokens for u in used),
        )


class TurnExpectations:
    """What one turn of a `TextCall` is expected to have done; each check raises AssertionError
    saying what the turn did instead."""

    def __init__(self, turn: TextTurn) -> None:
        self._turn = turn

    def tool_call(self, name: str, **args: JsonValue) -> None:
        """The talker called the tool `name`, with `args` among its arguments."""
        calls = self._turn.tool_calls
        for call in calls:
            if call.tool == name and all(call.arguments.get(k) == v for k, v in args.items()):
                return
        made = [(call.tool, dict(call.arguments)) for call in calls]
        raise AssertionError(f"turn {self._turn.turn_id} made no call of {name} {args}: {made}")

    def said(self, *, contains: str) -> None:
        """The reply the caller heard holds `contains`."""
        text = " ".join(clause.text for clause in self._turn.heard())
        if contains not in text:
            raise AssertionError(f"turn {self._turn.turn_id}'s reply said {text!r}")

    def blocked(self) -> None:
        """The output guard blocked a clause of the reply."""
        if not self._turn.blocked:
            raise AssertionError(f"the guard blocked no clause of turn {self._turn.turn_id}")

    def cancelled(self, tool: str) -> None:
        """The tool `tool` was cancelled, by the turn's words or a stop."""
        calls = self._turn.tool_calls
        if not any(call.tool == tool and call.outcome == "cancelled" for call in calls):
            made = [(call.tool, call.outcome) for call in calls]
            raise AssertionError(f"turn {self._turn.turn_id} cancelled no {tool}: {made}")

    def language(self, tag: LanguageTag) -> None:
        """The reply was in the language `tag`."""
        spoken = [clause.language for clause in self._turn.clauses if not clause.phrase]
        if not spoken or any(language != tag for language in spoken):
            raise AssertionError(f"turn {self._turn.turn_id}'s reply was in {spoken}, not {tag}")

    # What the turn did with an action (testing/text_actions.py), read from what the agent said
    # after it, whatever reply said it.

    def read_back(self, *, contains: str | None = None, **values: JsonValue) -> None:
        """The agent read a draft back after the turn, its summary said whole: one whose
        read-back holds `contains`, its draft holding `values`."""
        text_actions.expect_read_back(self._turn._reads, self._turn.turn_id, contains, values)

    def no_read_back(self) -> None:
        """The agent read no draft back after the turn."""
        text_actions.expect_no_read_back(self._turn._reads, self._turn.turn_id)

    def asked_again(self) -> None:
        """The agent asked again after the turn, in a read-back's ask-again line."""
        text_actions.expect_asked_again(self._turn._reads, self._turn.turn_id)

    def confirmed(self, name: str, **values: JsonValue) -> None:
        """The turn's words confirmed the action `name`, its draft holding `values`."""
        text_actions.expect_confirmed(self._turn._reads, self._turn.turn_id, name, values)

    def no_action(self) -> None:
        """The turn's words confirmed no action."""
        text_actions.expect_no_action(self._turn._reads, self._turn.turn_id)

    def action_ended(self, name: str, kind: OutcomeKind) -> None:
        """The action `name` the turn's words confirmed ended as `kind` (`done`, `failed`,
        `unknown`), and the agent said its `sending` line, then the outcome's."""
        text_actions.expect_ended(self._turn._reads, self._turn.turn_id, name, kind)

    def action_completed(self, name: str) -> None:
        """The action `name` the turn's words confirmed was done (`action_ended`, `done`)."""
        self.action_ended(name, "done")
