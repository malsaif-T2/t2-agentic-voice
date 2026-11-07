"""The stored overlaps of `poe uncertain` judged again under the session's rule at this commit
(plan 006's registration, U: U0 is "the rule (D-061)", which holds its one registered revision,
D-068, the session's default; plan 005's O1 and O2 ran before that revision).

Each variant of the stored dev overlap run is replayed over its reply through the `evals`
facade's `AudioCall`, as `poe overlap` plays it (overlap_run.py's `AT_S`, `TAIL_S` and
`ReplySpeech`), at real-time pace and with the run's settings, the library's defaults unless
`--set`, so the session's own rule decides it; its speech-to-text sends nothing and answers each
of the call's requests with the stored run's transcript of it, in order (`StoredSpeech`), as
plan 005's offline score of its revision read the stored transcripts. It spends nothing. The
call is held in the item's language, and an item of no language (silence, noise, the agent's
echo) in the reply's: Saudi Arabic when the reply holds Arabic letters, else English, as
overlap_plan.py's `overlap_of` picks it from the reply's language.

A variant is **reproduced** when its replay's requests, up to the one that decided it (all of
them when none did), are the stored run's, turn and part, in order, each then answered with its
own stored transcript. One that is not, one the replay could not play, and one with a stored
request that failed (no transcript of it) are counted apart (`unmatched`) and left out of U.
"""

from __future__ import annotations

import unicodedata
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Final

from t2_agentic_voice import VoiceSettings, get_logger
from t2_agentic_voice.ports import AudioClip, DataFlow, Transcript

from ole5_voice.evals.audio import read_wav
from ole5_voice.evals.overlap_card import OverlapScorecard
from ole5_voice.evals.overlap_run import (
    AT_S,
    REPLY_MARGIN_S,
    TAIL_S,
    Overlap,
    Replayer,
    ReplySpeech,
)
from ole5_voice.evals.overlap_score import Heard, OverlapResult, Verdict
from ole5_voice.evals.run_parts import Todo
from ole5_voice.evals.timing_run import TAGS, Tag
from ole5_voice.evals.worktree import refused

_FLOW: Final = DataFlow(
    provider="none", processed_in="this process", stored_in="nowhere", retention="none"
)
# How a replay is built: with `settings`, `stt` and `tts` (the `evals` facade's `AudioCall`).
ReplayerFactory = Callable[..., Replayer]
log = get_logger(__name__)


class StoredSpeech:
    """A speech-to-text that sends nothing: each request answered with the next of `heard`, a
    stored run's requests of the clip being replayed, its text and its no-speech probability;
    a request past them with no words."""

    name = "stored"
    data_flow = _FLOW

    def __init__(self) -> None:
        self.heard: list[Heard] = []

    async def transcribe(
        self, clip: AudioClip, *, language: str | None, prompt: str | None
    ) -> Transcript:
        if not self.heard:
            return Transcript(text="", language=language)
        found = self.heard.pop(0)
        text, no_speech = found.text or "", found.no_speech_prob
        return Transcript(text=text, language=language, no_speech_prob=no_speech)

    async def aclose(self) -> None:
        """Nothing is held open."""


def reproduced(verdict: Verdict, stored: Sequence[Heard]) -> bool:
    """Whether a replay's `verdict` asked the `stored` run's requests up to its deciding one
    (all of them when none decided), turn and part, in order."""
    asked = [(r.turn_id, r.part) for r in verdict.requests]
    kept = [(r.turn_id, r.part) for r in stored]
    deciding = (verdict.decided_turn, verdict.decided_by)
    if verdict.decided_by is not None:
        if deciding not in asked:
            return False
        asked = asked[: asked.index(deciding) + 1]
    return asked == kept[: len(asked)]


def _tag(result: OverlapResult) -> Tag:
    """The language a stored variant's call was held in (the module's docstring)."""
    if (tag := TAGS.get(result.language)) is not None:
        return tag
    arabic = any(unicodedata.name(c, "").startswith("ARABIC") for t in result.reply for c in t)
    return "ar-SA" if arabic else "en"


@dataclass
class Rejudged:
    """The stored run's variants judged again, in its order, and how many were not
    reproduced."""

    results: list[OverlapResult] = field(default_factory=list)
    unmatched: int = 0


async def rejudged(
    card: OverlapScorecard,
    todo: Mapping[str, Todo],
    build: ReplayerFactory,
    settings: VoiceSettings,
) -> Rejudged:
    """Each variant of `card` replayed under this commit's rule (the module's docstring), its
    audio `todo`'s by variant; the run's refusal for a variant `todo` does not hold."""
    if missing := sorted(r.variant for r in card.variants if r.variant not in todo):
        raise refused(
            f"the golden set holds no checked variant {missing[0]} of the stored run",
            "give --audio the roots of the stored run's recordings, in a checkout of its items",
        )
    speech, voice = StoredSpeech(), ReplySpeech()
    replayer = build(settings=settings, stt=speech, tts=voice)
    found = Rejudged()
    await replayer.start()
    try:
        for result in card.variants:
            again = await _replayed(replayer, speech, voice, result, todo[result.variant])
            if again is None:
                found.unmatched += 1
            else:
                found.results.append(again)
            log.info("rejudged", done=len(found.results) + found.unmatched, of=len(card.variants))
    finally:
        await replayer.aclose()
    log.info("rejudge_finished", variants=len(card.variants), unmatched=found.unmatched)
    return found


async def _replayed(
    replayer: Replayer,
    speech: StoredSpeech,
    voice: ReplySpeech,
    stored: OverlapResult,
    todo: Todo,
) -> OverlapResult | None:
    """`stored` replayed and judged again; None when it is not reproduced."""
    heard = stored.verdict.requests
    if any(r.failure is not None for r in heard):
        return None
    clip = AudioClip(pcm16=b"".join(read_wav(path).pcm16 for path in todo.request.segments))
    overlap = Overlap(
        todo=todo,
        expected=stored.expected,
        reply=stored.reply,
        reply_known=stored.reply_known,
        tag=_tag(stored),
        word_end_ms=stored.word_end_ms,
    )
    speech.heard = list(heard)
    voice.seconds = AT_S + clip.seconds + TAIL_S + REPLY_MARGIN_S
    try:
        replay = await replayer.over_reply(
            clip,
            reply=overlap.reply,
            language=overlap.tag,
            at_s=AT_S,
            tail_s=TAIL_S,
            word_end_ms=overlap.word_end_ms,
        )
    except ValueError:  # a reply no greeting may say, or a clip at another rate
        return None
    verdict = Verdict.model_validate(replay.model_dump(exclude={"stop_ms"}))
    return overlap.result("dev", verdict) if reproduced(verdict, heard) else None
