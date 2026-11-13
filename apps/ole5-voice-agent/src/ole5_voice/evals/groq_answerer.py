"""The `groq` answerer of `poe eval`: it asks Groq's Whisper through the library's speech-to-text
port, with the run's pacer and budget, in a module of its own as each answerer is.

It sends one request at a time, the starts paced to `--max-rpm`. A request the provider turns
away is asked again, up to `--max-attempts` times in all, after a pause: the larger of the
provider's `retry-after` and 20 s for a rate limit, 3 s for another failure that may pass, as
the prototype's scorer paused (`Ole5-chatbot/scripts/stt_eval.py`, lines 575-585); after the
last attempt, or on a refusal no retry can mend, the variant is a provider failure, an answer and
not an exception. A variant still running at `--variant-timeout-s` is stuck. Before each request
the run's `Budget` is charged what Groq bills for it, and a request that would take the run past
`--cap-usd` is never sent. Each request goes in the language the run's policy sends every one
in (run W's arm X sends `ar`, as an Arabic call does), or else the item's, with the policy's
Whisper prompt for that language, if it holds one (run W's arm W1). No line it logs holds a
transcript or names a variant.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping, Sequence
from contextlib import asynccontextmanager
from dataclasses import dataclass, field

from t2_agentic_voice import ProviderError, get_logger
from t2_agentic_voice.ports import AudioClip, SpeechToText, Transcript
from t2_agentic_voice.tracing import Tracing

from ole5_voice.evals.audio import leading_window, read_wav
from ole5_voice.evals.models import Variant
from ole5_voice.evals.reference_answerer import measured
from ole5_voice.evals.runs import (
    Answer,
    AnswerRequest,
    Outcome,
    Request,
    SegmentAnswer,
    Window,
    cost_usd,
)
from ole5_voice.evals.windows import Measure

# Groq bills each request at least 10 s of audio (plan 002, "The cost and the time"; the
# design's 10.4): the library's own minimum (core/settings/stt.py's `WHISPER_MIN_BILLED_S`),
# which a test ties it to. The answerer
# charges a request before it is sent, so it cannot take the minimum from the transcript.
GROQ_MINIMUM_S = 10.0
RATE_LIMIT_PAUSE_S = 20.0  # the least pause after a rate limit (stt_eval.py, line 581)
RETRY_PAUSE_S = 3.0  # the pause after another failure that may pass (stt_eval.py, line 585)

log = get_logger(__name__)

Clock = Callable[[], float]  # seconds, from any start: `time.perf_counter`, monotonic and fine
Sleep = Callable[[float], Awaitable[None]]
_Send = Callable[[AudioClip, str | None], Awaitable[Transcript]]


class CapReachedError(Exception):
    """The next request would take the run's billed total past `--cap-usd`: the run ends
    between requests, incomplete."""


@dataclass
class Budget:
    """What a run has been billed, and the cap no request may take it past."""

    price_per_hour_usd: float
    cap_usd: float | None = None
    billed_seconds: float = 0.0
    requests: int = 0

    @property
    def cost_usd(self) -> float:
        return cost_usd(self.billed_seconds, self.price_per_hour_usd)

    def charge(self, seconds: float) -> None:
        """Count one request billed `seconds`, before it is sent; CapReachedError, with nothing
        counted, when the run's cost would then pass the cap."""
        cost = cost_usd(self.billed_seconds + seconds, self.price_per_hour_usd)
        if self.cap_usd is not None and cost > self.cap_usd:
            raise CapReachedError
        self.billed_seconds += seconds
        self.requests += 1


def least_billed(requests: Sequence[AnswerRequest]) -> float:
    """The fewest seconds Groq bills for `requests`, each segment sent once: the cap's check
    before a run starts (a retry, or a request over the cap, comes on top)."""
    return sum(max(GROQ_MINIMUM_S, read_wav(path).seconds) for r in requests for path in r.segments)


@dataclass(frozen=True)
class Policy:
    """How the `groq` answerer asks: `--max-attempts`, `--max-rpm`, `--variant-timeout-s`; the
    language every request goes in (`language`; None: the item's, as the run's hint gives it);
    and the Whisper prompt sent with each language, by its code (`prompts`; none for another)."""

    max_attempts: int = 4
    max_rpm: int = 20
    variant_timeout_s: float = 120.0
    language: str | None = None
    prompts: Mapping[str, str] = field(default_factory=dict)


class Pacer:
    """Spaces the starts of requests at least 60 / `max_rpm` seconds apart."""

    def __init__(self, max_rpm: int, clock: Clock, sleep: Sleep) -> None:
        self._gap = 60 / max_rpm
        self._clock, self._sleep = clock, sleep
        self._last: float | None = None

    async def next(self) -> None:
        """Return when the next request may start."""
        if self._last is not None and (delay := self._last + self._gap - self._clock()) > 0:
            await self._sleep(delay)
        self._last = self._clock()


class GroqAnswerer:
    """Asks the speech-to-text port for each segment of a variant, or for each of its windows,
    in the language its policy sends or the run hints, with its policy's prompt for it."""

    name = "groq"
    spends = True
    needs_audio = True

    def __init__(
        self,
        stt: SpeechToText,
        *,
        model: str,
        policy: Policy,
        budget: Budget,
        measure: Measure | None,
        reuse: Mapping[Variant, str],
        tracing: Tracing | None,
        run_name: str,
        clock: Clock,
        sleep: Sleep,
    ) -> None:
        self._stt, self._model, self._policy, self._budget = stt, model, policy, budget
        self._measure, self._reuse, self._tracing, self._run = measure, reuse, tracing, run_name
        self._clock, self._sleep = clock, sleep
        self._pacer = Pacer(policy.max_rpm, clock, sleep)
        self._log: list[Request] = []  # the requests of the variant being answered
        self._pending: tuple[int, int, float] | None = None  # segment, attempt, billed seconds
        self._started = 0.0  # when the request in flight was sent

    async def answer(self, variant: Variant, request: AnswerRequest) -> Answer:
        self._log, self._pending = [], None
        try:
            async with asyncio.timeout(self._policy.variant_timeout_s):
                return await self._answer(variant, request)
        except TimeoutError:
            pending = self._pending
            stuck = () if pending is None else (self._request(pending, "stuck"),)
            return Answer(variant=variant.id, requests=(*self._log, *stuck), failure="stuck")

    async def aclose(self) -> None:
        """Close the speech-to-text adapter, through the port's own close."""
        await self._stt.aclose()

    async def _answer(self, variant: Variant, request: AnswerRequest) -> Answer:
        async with self._sender() as send:
            if request.windows_ms:
                return await self._windows(variant, request, send)
            parts: list[tuple[float, Transcript]] = []
            for index, path in enumerate(request.segments):
                wav = read_wav(path)
                clip = AudioClip(pcm16=wav.pcm16, sample_rate=wav.sample_rate)
                transcript = await self._ask(send, clip, self._language(request), index)
                if transcript is None:
                    return Answer(variant=variant.id, requests=tuple(self._log), failure="provider")
                parts.append((wav.seconds, transcript))
        return _combined(variant.id, parts, tuple(self._log))

    async def _windows(self, variant: Variant, request: AnswerRequest, send: _Send) -> Answer:
        """The windows of the first segment. One at least as long as the clip is not sent again
        when the run was given the clip's answer (`reuse`); otherwise the whole clip is sent."""
        measure = measured(self._measure)
        wav = read_wav(request.segments[0])
        found: list[Window] = []
        for ms in request.windows_ms:
            known = self._reuse.get(variant) if ms >= wav.milliseconds else None
            if known is not None:
                found.append(measure(variant.reference, ms, known, True))
                continue
            clip = AudioClip(pcm16=leading_window(wav, ms), sample_rate=wav.sample_rate)
            transcript = await self._ask(send, clip, self._language(request), 0)
            if transcript is None:
                return Answer(variant=variant.id, requests=tuple(self._log), failure="provider")
            found.append(measure(variant.reference, ms, transcript.text, False))
        return Answer(variant=variant.id, requests=tuple(self._log), windows=tuple(found))

    def _language(self, request: AnswerRequest) -> str | None:
        """The language a variant's requests go in: the policy's, else the request's."""
        return self._policy.language or request.language

    async def _ask(
        self, send: _Send, clip: AudioClip, language: str | None, segment: int
    ) -> Transcript | None:
        """One clip's transcript, asked again while the provider turns it away with a failure
        that may pass; None after the last attempt, or after a refusal no retry mends."""
        billed = max(GROQ_MINIMUM_S, clip.seconds)
        attempt = 0
        while True:
            attempt += 1
            await self._pacer.next()
            self._budget.charge(billed)
            pending = self._pending = (segment, attempt, billed)
            self._started = self._clock()
            try:
                transcript = await send(clip, language)
            except ProviderError as error:
                self._log.append(self._request(pending, error.kind))
                if not error.retryable or attempt >= self._policy.max_attempts:
                    log.warning("provider_failure", kind=error.kind, attempts=attempt)
                    return None
                pause = RETRY_PAUSE_S
                if error.kind == "rate_limited":
                    pause = max(error.retry_after_s or 0.0, RATE_LIMIT_PAUSE_S)
                log.warning("request_refused", kind=error.kind, attempt=attempt, pause_s=pause)
                await self._sleep(pause)
                continue
            self._log.append(self._request(pending, "ok"))
            return transcript

    def _request(self, pending: tuple[int, int, float], outcome: Outcome) -> Request:
        """The request in flight, ended with `outcome` (`stuck` when the deadline came first)."""
        segment, attempt, billed = pending
        self._pending = None
        return Request(
            segment=segment,
            attempt=attempt,
            latency_ms=max(0.0, (self._clock() - self._started) * 1000),
            billed_seconds=billed,
            outcome=outcome,
        )

    @asynccontextmanager
    async def _sender(self) -> AsyncIterator[_Send]:
        """How a request is sent: through the port, inside a speech-to-text span under the
        variant's root span when the run is traced (its `session.id` the run's name)."""
        tracing = self._tracing
        if tracing is None:
            yield self._send
            return
        with tracing.turn(session_id=self._run, name="golden_variant") as root:

            async def traced(clip: AudioClip, language: str | None) -> Transcript:
                with tracing.speech_to_text(
                    root, model=self._model, language=language, audio_seconds=clip.seconds
                ) as span:
                    transcript = await self._send(clip, language)
                    span.record(
                        text=transcript.text,
                        language=transcript.language,
                        billed_seconds=transcript.billed_seconds,
                    )
                return transcript

            yield traced

    async def _send(self, clip: AudioClip, language: str | None) -> Transcript:
        prompt = None if language is None else self._policy.prompts.get(language)
        return await self._stt.transcribe(clip, language=language, prompt=prompt)


def _combined(
    variant: str, parts: Sequence[tuple[float, Transcript]], requests: tuple[Request, ...]
) -> Answer:
    """One variant's answer from its segments' transcripts, joined with a space; for a variant
    of several, each segment's own answer too, and the language of the longest."""
    text = " ".join(t.text.strip() for _, t in parts if t.text.strip())
    if len(parts) == 1:
        only = parts[0][1]
        return Answer(
            variant=variant,
            text=text,
            language=only.language,
            confidence=only.confidence,
            no_speech_prob=only.no_speech_prob,
            requests=requests,
        )
    return Answer(
        variant=variant,
        text=text,
        language=max(parts, key=lambda part: part[0])[1].language,
        confidence=_by_length([(s, t.confidence) for s, t in parts]),
        no_speech_prob=_by_length([(s, t.no_speech_prob) for s, t in parts]),
        segments=tuple(
            SegmentAnswer(
                text=t.text,
                language=t.language,
                confidence=t.confidence,
                no_speech_prob=t.no_speech_prob,
            )
            for _, t in parts
        ),
        requests=requests,
    )


def _by_length(values: Sequence[tuple[float, float | None]]) -> float | None:
    """The mean of a value over the segments that have one, each weighted by its length, as the
    prototype weighs Whisper's segments (`Ole5-chatbot/src/ole5_chat/voice/stt.py`, lines
    249-252); None when none has one."""
    known = [(seconds, value) for seconds, value in values if value is not None]
    total = sum(seconds for seconds, _ in known)
    return sum(seconds * value for seconds, value in known) / total if total else None
