"""Where a `TextCall`'s read-backs play (testing/text_call.py; plan 007): which clauses of the
agent's replies say a draft's summary and its closing question, read from the session's
`Playback` (each clause's caption) against the read-backs the talker asked for (each
`ReadBackPlan`), so that a turn can be said over either part (`during`), a fault armed for a
summary, and the call's checks told when a summary played whole.

**A reading** of a plan is a run of clauses of one reply whose captions, joined, say the plan's
summary whole, and the run after it that says its closing question, if any. A caption is
compared folded (no case, no space, no mark), and a line in each form it may be said in: its
plain text, its spoken form, and either as the session may say it, since the session says a long
line in several clauses, each captioned as said (voice/session/open_reply.py's `speech_of`): its
key combinations as their keys or as written (`tts.spoken_key_combinations`), then its numbers
by the speaking rules or in either Arabic register (`tts.spoken_numbers`). A reply said again
at the caller's request reads the same way.

**The runtime's own lines** (the read-back, `asked_again`, `declined`, `sending`, an outcome)
are templates, which the output guard's rules never check (the design's 8.2): `templates`
gives their folded forms, `is_template` whether a caption is one of them or a piece of one.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from functools import lru_cache
from typing import Literal

from t2_agentic_voice.core.settings.tts import LanguageTag
from t2_agentic_voice.domain.action_lines import ReadBackPlan, SpokenLine
from t2_agentic_voice.domain.text.arabic_numbers import Register
from t2_agentic_voice.domain.text.keys import speak_keys
from t2_agentic_voice.domain.text.speaking import speak_digits
from t2_agentic_voice.domain.text.spoken_text import speak_text
from t2_agentic_voice.voice.protocol import ClauseIndex, ReplyId
from t2_agentic_voice.voice.session.playback import Playback, Reply

# The two parts of a read-back a turn may be said over.
Part = Literal["summary", "question"]

# The registers a line's numbers may be said in: the tag's own (None), or either Arabic one.
_REGISTERS: tuple[Register | None, ...] = (None, "saudi", "msa")


def fold(text: str) -> str:
    """`text` as captions are compared: its letters and digits alone, case folded."""
    return "".join(character for character in text.casefold() if character.isalnum())


def _said(text: str, language: LanguageTag) -> set[str]:
    """`text` as the session may say it in `language`, under any of the settings that shape
    it (the module's docstring)."""
    found: set[str] = set()
    for keyed in {text, speak_keys(text, language=language)}:
        found |= {keyed, speak_digits(keyed, language=language)}
        found |= {speak_text(keyed, language=language, register=r) for r in _REGISTERS}
    return found


@lru_cache(maxsize=1024)
def forms(line: SpokenLine, language: LanguageTag) -> frozenset[str]:
    """Each folded form `line`, said in `language`, may be captioned in (the module's
    docstring)."""
    said = _said(line.text, language) | _said(line.spoken, language)
    return frozenset(fold(text) for text in said) - {""}


@dataclass(frozen=True, kw_only=True)
class Reading:
    """One reading of `plan`: the reply that said it, the clauses of its summary and those of
    its closing question (none when the reply did not go on to it)."""

    plan: ReadBackPlan
    reply_id: ReplyId
    summary: tuple[ClauseIndex, ...]
    question: tuple[ClauseIndex, ...] = ()


def _run(captions: Sequence[str], start: int, whole: frozenset[str]) -> int | None:
    """Where the run of `captions` from `start` that says one of `whole` ends (one past it);
    None when none does."""
    joined = ""
    for index in range(start, len(captions)):
        joined += captions[index]
        if joined in whole:
            return index + 1
        if not any(form.startswith(joined) for form in whole):
            return None
    return None


def _readings_in(reply: Reply, plans: Sequence[ReadBackPlan]) -> list[Reading]:
    captions = [fold(clause.caption) for clause in reply.clauses]
    found: list[Reading] = []
    start = 0
    while start < len(captions):
        for plan in reversed(plans):  # the newest plan first, as a correction's is
            end = _run(captions, start, forms(plan.summary, plan.language))
            if end is None:
                continue
            after = _run(captions, end, forms(plan.question, plan.language))
            question = () if after is None else tuple(range(end, after))
            found.append(
                Reading(
                    plan=plan,
                    reply_id=reply.reply_id,
                    summary=tuple(range(start, end)),
                    question=question,
                )
            )
            start = after or end
            break
        else:
            start += 1
    return found


def readings(playback: Playback, plans: Sequence[ReadBackPlan]) -> tuple[Reading, ...]:
    """Every reading of `plans` the session has asked for so far, oldest first."""
    if not plans:
        return ()
    replies = (playback.reply(reply_id) for reply_id in range(playback.next_id))
    return tuple(r for reply in replies if reply is not None for r in _readings_in(reply, plans))


def part_at(found: Iterable[Reading], reply_id: ReplyId, clause: ClauseIndex) -> Part | None:
    """The part of a read-back clause `clause` of reply `reply_id` says, None for any other."""
    for reading in found:
        if reading.reply_id == reply_id and clause in reading.summary:
            return "summary"
        if reading.reply_id == reply_id and clause in reading.question:
            return "question"
    return None


def playing(playback: Playback, plans: Sequence[ReadBackPlan]) -> Part | None:
    """The part of a read-back that plays now, None when none does."""
    now = playback.playing()
    return None if now is None else part_at(readings(playback, plans), now[0].reply_id, now[1])


def summary_played_at(playback: Playback, reading: Reading) -> float | None:
    """When the reading's summary ended, played whole: every clause of it played, none cut
    short, each with audio; None otherwise, or while it plays. A stop that cut its reply after
    the summary changes none of that, as for the session's receipt (voice/session/read_back.py):
    a stop over the summary leaves a clause of it unplayed or cut short."""
    reply = playback.reply(reading.reply_id)
    if reply is None:
        return None
    clauses = [reply.clauses[index] for index in reading.summary]
    if any(not c.played or c.cut_short or c.chunks == 0 or c.played_at is None for c in clauses):
        return None
    return max(c.played_at for c in clauses if c.played_at is not None)


def templates(
    plans: Iterable[ReadBackPlan], outcomes: Iterable[tuple[SpokenLine, LanguageTag]]
) -> frozenset[str]:
    """The folded forms of every line of the runtime's own the call may have said: each plan's
    read-back, ask-again, declined and sending lines, and each outcome's line, in its
    language."""
    found: set[str] = set()
    for line, language in outcomes:
        found |= forms(line, language)
    for plan in plans:
        for line in (plan.summary, plan.question, plan.asked_again, plan.declined, plan.sending):
            found |= forms(line, plan.language)
    return frozenset(found)


def is_template(caption: str, folded: frozenset[str]) -> bool:
    """Whether `caption` is one of the runtime's own lines `folded` holds, or a piece of one."""
    mine = fold(caption)
    return bool(mine) and any(mine in line for line in folded)
