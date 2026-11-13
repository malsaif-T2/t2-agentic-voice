"""What the tests of an action's read-back in the session share: a read-back plan of the tests'
own, a talker that reads it back as its reply to turn 0, the yes rule's words as the tests give
them (`CONSENT`, patched where the session calls `consent_words`, through conftest.py's
`consent`), and the steps a read-back's reply plays through.

Turn 0's reply is reply 1 (the greeting is reply 0): its clause 0 the summary and clause 1 the
closing question, one request each. The texts are written for these tests, none a golden item.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from t2_agentic_voice.agent.events import ReadBackRequested
from t2_agentic_voice.agent.talker import ReplyDone
from t2_agentic_voice.core.conversation import TalkerTurn
from t2_agentic_voice.core.yes_inputs import ReadBackReceipt
from t2_agentic_voice.domain.action_lines import ReadBackPlan, SpokenLine
from t2_agentic_voice.domain.yes_words import ConsentWords
from t2_agentic_voice.voice.protocol import State
from t2_agentic_voice.voice.session.call import CallSession

from tests.t2_agentic_voice.session_fakes import FakeSessionIO
from tests.t2_agentic_voice.voice.session.overlap_support import overlap_part
from tests.t2_agentic_voice.voice.session.session_support import greeted, sent
from tests.t2_agentic_voice.voice.session.talker_support import Step, answer, settle, talked

ACTION = "open_made_up_request"
DRAFT = '{"issue": "made-up issue", "urgency": "made-up"}'
SUMMARY = "Made-up summary of the draft, request 4521 for the printer."
SUMMARY_SPOKEN = "Made-up summary of the draft, request four five two one for the printer."
QUESTION = "Made-up closing question, shall I go ahead?"
ASKED = "Made-up line asking again."
REQUEST = "made-up request for the agent to act"


def _line(text: str, spoken: str | None = None) -> SpokenLine:
    return SpokenLine(text=text, spoken=spoken or text)


PLAN = ReadBackPlan(
    action=ACTION,
    tool_call_id="call-1",
    draft_json=DRAFT,
    summary=_line(SUMMARY, SUMMARY_SPOKEN),
    question=_line(QUESTION),
    asked_again=_line(ASKED),
    declined=_line("Made-up declined line."),
    sending=_line("Made-up sending line."),
    language="en",
    max_attempts=2,
)
# The yes rule's words, as the tests give them in place of the presets': made-up words but
# for the plain yes, and the call language's listening sounds are the preset's (domain/words.py).
CONSENT = ConsentWords(
    yes=("yes", "made-up-yes"),
    send=("send it", "made-up-send"),
    no=("no",),
    fillers=("please",),
)
YES_TEXT = "yes please, send it"  # yes and send words and a filler only
CALLER_WORDS = "made-up correction of several words"  # real words over the read-back


def reads_back(turn: TalkerTurn) -> Sequence[Step]:
    """Turn 0's reply reads `PLAN` back, and says nothing else; a later turn's says one clause."""
    if turn.turn_id == 0:
        return [ReadBackRequested(plan=PLAN), ReplyDone()]
    return answer("Made-up answer.")


async def asked(io: FakeSessionIO) -> None:
    """The call is greeted, and the caller's turn 0, said while the agent is silent, has the
    talker read `PLAN` back: reply 1 asked for, nothing of it played yet."""
    await greeted(io)
    await talked(io, 0, REQUEST)


async def clause(io: FakeSessionIO, index: int, *, played: bool = True, **given: Any) -> None:
    """Reply 1's clause `index` begins to play (its request reported, its first audio queued),
    and, when `played`, plays whole 0.5 s later, with what `given` says of its audio."""
    await io.synthesizing(1, index)
    await io.clause_queued(1, index)
    await io.clock.advance(0.5)
    if played:
        await io.clause_played(1, index, **{"audio_s": 2.0, **given})


async def read_whole(io: FakeSessionIO) -> None:
    """Reply 1's summary, then its closing question, play whole."""
    await clause(io, 0)
    await clause(io, 1)


async def over(io: FakeSessionIO, turn_id: int, text: str) -> None:
    """The caller says `text` over the reply playing (turn `turn_id`): its whole overlap heard,
    then the turn closes and its own transcript reuses it."""
    await io.turn_opened(turn_id)
    await overlap_part(io, turn_id, text)
    await io.turn_closed(turn_id)
    await io.transcribed(turn_id, text, language="en")
    await settle()


def states(io: FakeSessionIO) -> list[str]:
    """The states the client was shown, in order."""
    return [message.state for message in sent(io, State)]


def receipt(session: CallSession, speech_at: float | None) -> ReadBackReceipt | None:
    """The receipt the session builds now for a turn whose speech began at `speech_at`, as the
    yes rule's caller asks for it."""
    return session._interrupter.receipt(speech_at)
