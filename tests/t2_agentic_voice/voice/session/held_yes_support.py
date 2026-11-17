"""What the held-yes tests share (test_read_back_held_yes.py and test_read_back_held_yes_more.py):
the made-up words, the rule as they script it, the call under the setting, and the moments of
its read-back."""

from __future__ import annotations

from typing import Any

from t2_agentic_voice.core.config import VoiceSettings
from t2_agentic_voice.core.events import ConfirmationAnswered
from t2_agentic_voice.domain.text.invisible import provider_text
from t2_agentic_voice.domain.words import PRESET_WORDS
from t2_agentic_voice.voice.session.call import CallSession

from tests.t2_agentic_voice.session_fakes import FakeSessionIO
from tests.t2_agentic_voice.voice.session.overlap_support import (
    NEW_WORDS,
    REPEAT,
    REPEAT_TEXT,
    STOP,
    FakeRule,
    two_step,
)
from tests.t2_agentic_voice.voice.session.read_back_support import (
    CALLER_WORDS,
    PLAN,
    SUMMARY_SPOKEN,
    asked,
    clause,
)
from tests.t2_agentic_voice.voice.session.session_support import emitted, speaks
from tests.t2_agentic_voice.voice.session.talker_support import AGENT, FakeTalker, settle
from tests.t2_agentic_voice.voice.session.yes_support import FakeJobs, confirm_call

SENDING = [provider_text(PLAN.sending.spoken)]
LISTENING_WORD = PRESET_WORDS["en"].backchannel[0]
BARE_YES = "made-up-yes"  # CONSENT's own yes word, said alone
OTHER = "made-up-word"  # one word on no list, which the fake rule lets go on
QUESTION_BACK = "made-up question?"
KHALAS = "خلاص"  # khalas, that's it: a stop word of the call's here, and a filler
KHALAS_YES = f"{KHALAS} yes"
ASKS = AGENT.model_copy(update={"ask_on_unlisted_answers": True})
UNPLACED = "sounds fine to me"  # words on none of CONSENT's lists
ECHO = provider_text(SUMMARY_SPOKEN)  # the summary heard back


def scripted_rule(rule: FakeRule) -> FakeRule:
    """The rule as these tests script it: real words stop the agent, and so do khalas and
    khalas beside a yes, as the real rule's stop word does; a repeat request repeats."""
    rule.script |= {
        CALLER_WORDS: NEW_WORDS,
        REPEAT_TEXT: REPEAT,
        KHALAS: STOP,
        KHALAS_YES: STOP,
    }
    return rule


def settings_for(settings: VoiceSettings, on: bool) -> VoiceSettings:
    """`settings` under two_step, the setting `on` or off, khalas a stop word of the call's."""
    words = settings.words.model_copy(update={"stop": {"en": (KHALAS,)}})
    return two_step(settings, yes_over_read_back=on).model_copy(update={"words": words})


def call(
    settings: VoiceSettings, on: bool = True, **given: Any
) -> tuple[FakeSessionIO, CallSession, FakeTalker, FakeJobs]:
    jobs = FakeJobs()
    io, session, talker = confirm_call(settings_for(settings, on), jobs, **given)
    return io, session, talker, jobs


def answered(io: FakeSessionIO) -> list[tuple[int | None, str, str]]:
    return [(e.turn_id, e.decision, e.by) for e in emitted(io, ConfirmationAnswered)]


def said_in(io: FakeSessionIO, reply_id: int) -> list[str]:
    return [speak.text for speak in speaks(io, reply_id)]


async def summary_plays(io: FakeSessionIO) -> None:
    """The read-back (reply 1) is asked for, and its summary's first audio queued, 0.5 s ago."""
    await asked(io)
    await clause(io, 0, played=False)


async def summary_ends(io: FakeSessionIO, **given: Any) -> None:
    await io.clause_played(1, 0, **{"audio_s": 2.0, **given})
    await settle()
