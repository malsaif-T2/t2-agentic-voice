"""A read-back whose call moved into another language before it was answered (D-038's
amendment; docs/SECURITY.md, invariant 1), for yes_turns.py.

Under `stt.live_language = "detected"` the call may move while it is confirming: a turn heard in
the other language, a spoken switch request, or the talker's `switch_language` tool
(call_language.py). The read-back said before the move is then never confirmed: the turn that
answers it is not the yes rule's. The read-back is read again in the new language, from the same
draft (agent/read_back_language.py), as the reply answering that turn, in place of the old one,
so only a yes heard after the new summary played whole, with its own receipt, confirms it. The
yes rule's evidence is unchanged: the turn's own heard words, which no move rewrites. When the
action cannot be read in the new language, it is declined as a correction, and the talker
answers the turn. Under any other `stt.live_language` the call never moves, so nothing here
happens (GP-18). A read-back said again at the caller's request is said by `read_again` too.
"""

from __future__ import annotations

from t2_agentic_voice.agent.read_back_language import read_back_in
from t2_agentic_voice.core.events import ReplyId, TurnId
from t2_agentic_voice.core.logging import get_logger
from t2_agentic_voice.core.settings.words import primary_code
from t2_agentic_voice.domain.action_lines import ReadBackPlan
from t2_agentic_voice.voice.session.io import CallSetup
from t2_agentic_voice.voice.session.playback import Playback
from t2_agentic_voice.voice.session.read_back import Confirming
from t2_agentic_voice.voice.session.read_back_times import ReadBack
from t2_agentic_voice.voice.session.report import TurnLog
from t2_agentic_voice.voice.session.speaker import Speaker

_log = get_logger(__name__)


def moved_since(setup: CallSetup, playback: Playback, read_back: ReadBack) -> bool:
    """Whether the call moved into another language after `read_back` was said: a move on a
    turn later than the one its reply answers, to a language not the read-back's."""
    now, reply = setup.now, playback.reply(read_back.reply_id)
    if now.moved_on is None or reply is None or reply.turn_id is None:
        return False
    return now.moved_on > reply.turn_id and primary_code(read_back.plan.language) != now.primary


async def read_moved(
    setup: CallSetup,
    speaker: Speaker,
    confirming: Confirming,
    turn: TurnLog,
    plan: ReadBackPlan,
    at: float,
) -> bool:
    """`plan`, read back before the call moved, read again in the call's language as the reply
    answering `turn`, at `at` (the module's docstring): True when it is; False when it cannot
    be, the read-back then declined as a correction, for the talker to answer the turn."""
    tag = setup.now.tag
    again = read_back_in(setup.agent, plan, tag)
    said = again is not None
    _log.info(
        "read_back_moved", call_id=setup.call_id, turn_id=turn.turn_id, language=tag, said=said
    )
    if again is None:
        confirming.decline(turn.turn_id, "correction")
        return False
    turn.reply_id = await read_again(speaker, confirming, again, turn_id=turn.turn_id, at=at)
    return True


async def read_again(
    speaker: Speaker, confirming: Confirming, plan: ReadBackPlan, *, turn_id: TurnId, at: float
) -> ReplyId:
    """Say `plan`'s read-back again, at the caller's request or in the call's new language, as a
    reply of its own answering `turn_id`, written whole at once: the current read-back, the
    earlier one void; its reply's number."""
    confirming.repeated()
    reply = await speaker.open_reply(at, turn_id=turn_id)
    await confirming.read(reply, plan, at)
    await reply.finish(at)
    return reply.reply_id
