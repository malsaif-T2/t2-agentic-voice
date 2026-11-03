"""The measuring part of a `poe overlap` run (`overlap.py`; plan 005's registration, the arm O):
each overlap clip of the run, its verdict from the `reference` answerer or from the replay
through the `evals` facade's `AudioCall`, and its result judged (overlap_score.py).

**The reference answerer** gives each clip the verdict its kind should have, the agent's last
audio frame at the clip's labelled word end (or, with none, at its speech's stop, the clip's
start), and no request: every verdict right and every stop 0 ms, the harness checking itself
inside `poe check`, reading no audio and sending nothing.

**The replay** plays each clip `AT_S` into a reply, as a fresh call, with `TAIL_S` of silence
after it (the registration's 1 s and 4.5 s), at real-time pace, through the real speech-to-text
and a text-to-speech that sends nothing (`ReplySpeech`), whose reply outlasts the clip and its
tail by `REPLY_MARGIN_S`. Before each clip the run waits until its pacer has room for the most a
clip is budgeted to send (`STT_PER_VARIANT`: an overlap's window and whole parts and its turn's
own), at the run's Whisper requests a minute (`--stt-rpm`, 10 by default, half the published 20:
plan 003's Track H), and refuses to start one whose budgeted cost would take the run past
`--cap-usd`. A clip one of whose requests met a rate limit is played again after
`RATE_LIMIT_PAUSE_S`, up to `MAX_ATTEMPTS` calls in all, every call's requests counted on the
pacer and in the spend, each billed as Groq bills Whisper, at least 10 s.

A run's results are kept as they come (`Progress`): a dev run's each written as it finishes, to
`RESULTS_FILE`, with a progress line of identifiers and verdicts, never a transcript; a held-out
run's counted only.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final, Literal, Protocol

from t2_agentic_voice import get_logger
from t2_agentic_voice.evals import OverlapReplay
from t2_agentic_voice.ports import AudioChunk, AudioClip, DataFlow, SpeechToText

from ole5_voice.evals.audio import read_wav
from ole5_voice.evals.groq_answerer import GROQ_MINIMUM_S, Sleep
from ole5_voice.evals.models import Split
from ole5_voice.evals.overlap_score import Action, OverlapResult, Verdict, judge
from ole5_voice.evals.pacers import MinutePacer
from ole5_voice.evals.run_parts import Todo
from ole5_voice.evals.runs import cost_usd

AT_S: Final = 1.0  # how far into the reply each clip starts (the registration's O)
TAIL_S: Final = 4.5  # the silence after it
REPLY_MARGIN_S: Final = 2.0  # how long the reply plays on after the tail (the agent's value)
RESULTS_FILE: Final = "results.jsonl"  # a dev run's results, each as it finishes
STT_PER_VARIANT: Final = 3  # window, whole overlap and the turn's own request, at most
MAX_ATTEMPTS: Final = 3
RATE_LIMIT_PAUSE_S: Final = 60.0  # a whole pacer window, the per-minute limit's own
# The text-to-speech's audio: a quiet tone, never silence, which Pipecat would mark unusable
# (plan 003's appendix, item 9), at the pipeline's output rate, in chunks of `_CHUNK_S`.
_RATE: Final = 24_000
_CHUNK_S: Final = 0.2
_TONE: Final = (600).to_bytes(2, "little", signed=True) + (-600).to_bytes(2, "little", signed=True)
_FLOW: Final = DataFlow(
    provider="none", processed_in="this process", stored_in="nowhere", retention="none"
)
# The library's language tags a replayed call is held in.
Tag = Literal["ar-SA", "ar", "en"]
# Why a run stopped before its last clip.
Stopped = Literal["cap", "interrupted"]
log = get_logger(__name__)


class ReplySpeech:
    """The replay's text-to-speech: every text said as `seconds` of a quiet tone, sending
    nothing; a run sets `seconds` before each clip so the reply outlasts it."""

    name = "none"
    data_flow = _FLOW

    def __init__(self, seconds: float = AT_S + TAIL_S + REPLY_MARGIN_S) -> None:
        self.seconds = seconds

    def max_chars(self, language: str) -> int | None:
        return None

    async def synthesize(self, text: str, *, language: str) -> AsyncIterator[AudioChunk]:
        samples = round(self.seconds * _RATE)
        pcm = (_TONE * (samples // 2 + 1))[: samples * 2]
        step = round(_CHUNK_S * _RATE) * 2
        for start in range(0, len(pcm), step):
            yield AudioChunk(pcm16=pcm[start : start + step], sample_rate=_RATE)

    async def check_language(self, language: str) -> None:
        """Every language is spoken, as a tone."""

    async def aclose(self) -> None:
        """Nothing is held open."""


class Replayer(Protocol):
    """The replay as a run uses it (the `evals` facade's `AudioCall`), or a test's fake."""

    async def start(self) -> None:
        """Start the calls' runtime once, before the first clip."""

    async def over_reply(
        self,
        clip: AudioClip,
        *,
        reply: Sequence[str],
        language: Tag,
        at_s: float,
        tail_s: float,
        word_end_ms: float | None = None,
    ) -> OverlapReplay:
        """Play `clip` over a reply of `reply`, and what came of it."""

    async def aclose(self) -> None:
        """Close the calls' runtime, after the last clip."""


class CapReachedError(Exception):
    """The next clip's budgeted cost would take the run past `--cap-usd`."""


@dataclass(frozen=True)
class Overlap:
    """One overlap clip to answer: its variant, what its kind should do, the reply it is played
    over and whether those are the texts that played over it when it was recorded, the language
    its call is held in, and its labelled word end (the first of `turn_ends_ms`), if marked."""

    todo: Todo
    expected: Action
    reply: tuple[str, ...]
    reply_known: bool
    tag: Tag
    word_end_ms: float | None

    def result(self, side: Split, verdict: Verdict, attempts: int = 1) -> OverlapResult:
        """The clip's result, its verdict judged."""
        item, variant = self.todo.item, self.todo.variant
        return OverlapResult(
            item=item.id,
            variant=variant.id,
            split=side,
            kind=item.kind,
            language=item.language,
            device=variant.device,
            expected=self.expected,
            reply=self.reply,
            reply_known=self.reply_known,
            word_end_ms=self.word_end_ms,
            attempts=attempts,
            verdict=verdict,
            judged=judge(self.expected, verdict, self.word_end_ms),
        )


def reference(overlap: Overlap) -> Verdict:
    """The `reference` answerer's verdict: the expected action, the `Interrupted` kind it
    gives, and, for a stop, the last frame at the labelled word end, else at the clip's start."""
    expected, kind = overlap.expected, overlap.todo.item.kind
    if expected == "go_on":
        return Verdict(opened=True, action="go_on", kind="false")
    given = "stop" if kind == "stop_word" else "correction" if kind == "correction" else "new_words"
    end = 0.0 if overlap.word_end_ms is None else overlap.word_end_ms
    return Verdict(opened=True, action=expected, kind=given, speech_stop_ms=end, last_audio_ms=end)


class Progress:
    """The results so far, each written and logged as it comes (counts only when held out)."""

    def __init__(self, total: int, results_file: Path | None) -> None:
        self.total, self.results_file = total, results_file
        self.results: list[OverlapResult] = []
        self.stopped: Stopped | None = None

    def add(self, result: OverlapResult) -> None:
        self.results.append(result)
        done = len(self.results)
        if self.results_file is None:
            log.info("progress", done=done, of=self.total)
            return
        with self.results_file.open("a", encoding="utf-8", newline="\n") as file:
            file.write(result.model_dump_json() + "\n")
        judged = result.judged
        stop_ms = (
            judged.from_mark_ms if judged.from_mark_ms is not None else judged.from_detector_ms
        )
        log.info(
            "variant_done",
            done=done,
            of=self.total,
            item=result.item,
            variant=result.variant,
            expected=result.expected,
            action=result.verdict.action,
            right=judged.right,
            requests=judged.overlap_requests,
            stop_ms=None if stop_ms is None else round(stop_ms),
        )


@dataclass
class Measuring:
    """One run's replay: the replay itself, the speech-to-text it was built with (closed at the
    end), its text-to-speech, the Whisper pacer, the price and the cap, and what it spent."""

    replayer: Replayer
    stt: SpeechToText
    speech: ReplySpeech
    pacer: MinutePacer
    price_per_hour_usd: float
    cap_usd: float
    sleep: Sleep
    requests: int = 0
    billed_seconds: float = 0.0

    @property
    def spent_usd(self) -> float:
        return cost_usd(self.billed_seconds, self.price_per_hour_usd)

    async def variant(self, overlap: Overlap, side: Split) -> OverlapResult:
        """One clip's replay, played again while it meets a rate limit."""
        segments = overlap.todo.request.segments
        clip = AudioClip(pcm16=b"".join(read_wav(path).pcm16 for path in segments))
        attempts = 0
        while True:
            attempts += 1
            verdict = await self._call(clip, overlap)
            limited = any(r.failure == "rate_limited" for r in verdict.requests)
            if not limited or attempts >= MAX_ATTEMPTS:
                return overlap.result(side, verdict, attempts)
            log.warning("variant_rate_limited", attempt=attempts, pause_s=RATE_LIMIT_PAUSE_S)
            await self.sleep(RATE_LIMIT_PAUSE_S)

    async def _call(self, clip: AudioClip, overlap: Overlap) -> Verdict:
        """One paced call, refused at the cap, its requests counted."""
        await self.pacer.room_for(STT_PER_VARIANT)
        budget = STT_PER_VARIANT * max(GROQ_MINIMUM_S, clip.seconds)
        if self.spent_usd + cost_usd(budget, self.price_per_hour_usd) > self.cap_usd:
            raise CapReachedError
        self.speech.seconds = AT_S + clip.seconds + TAIL_S + REPLY_MARGIN_S
        replay = await self.replayer.over_reply(
            clip,
            reply=overlap.reply,
            language=overlap.tag,
            at_s=AT_S,
            tail_s=TAIL_S,
            word_end_ms=overlap.word_end_ms,
        )
        verdict = Verdict.model_validate(replay.model_dump(exclude={"stop_ms"}))
        self.pacer.count(len(verdict.requests))
        self.requests += len(verdict.requests)
        self.billed_seconds += sum(max(GROQ_MINIMUM_S, r.audio_s) for r in verdict.requests)
        return verdict

    async def aclose(self) -> None:
        await self.replayer.aclose()
        await self.stt.aclose()
