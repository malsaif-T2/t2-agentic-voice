"""A call's speech-to-text stream, in its bridge (voice/stt_bridge.py; plan 010's 5.1):
`CallStream`, under `stt.streaming`, for a provider that implements the streaming port
(domain/ports/transcript_stream.py), in a call whose every request names its current language
(`stt.live_language = "session"`, or a mode that runs as session). Otherwise the bridge holds
`StreamHooks`, which do nothing, and the call is heard as before.

- **Opened** at the session's `ListenIn` naming a language (the call's start), with that
  language's prompt, and opened again in the language a later `ListenIn` names. A turn goes by
  request until the stream is open and has heard `LEAD_S` of the call (Scribe processes nothing
  before its first 2 s).
- **Fed** what a request would hear: each turn's audio as it comes, from its pre-roll
  (`preroll_s`, the bridge's), and between turns as much silence, a pre-roll late, so its clock
  runs with the call's but no word of what no turn holds (an echo, a television) reaches a turn.
- **A streamed turn** (opened with the stream ready, and no overlap) has its `held` and `turn`
  requests answered by commits of the stream (voice/stt_streamed.py's `StreamedRequests`). Each
  commits the audio since the last commit, unless no speech came since the turn's last one, and
  its answer is the words of every commit the turn made, joined: a pause Smart Turn calls
  unfinished (D-120), or speech resumed in the hold, leaves its commit's words to the turn's next
  request, never handed alone, as a request sent again with the whole turn would hear them.
- **By request, as before:** an overlap turn (`overlap`), a turn opened before the stream was
  ready, and a turn whose audio since the last commit reached `SPAN_S` (Scribe commits on its
  own after about 36 s). Their audio, fed already, is committed as the turn closes, its words
  dropped so no later turn hears them (a turn open as the stream opened among them), as is the
  call's silence once `FLUSH_S` went with no commit, turn or speech (Scribe: every 20 to 30 s).
- **Lost:** a stream that fails (its connection, the provider's error, a commit unanswered within
  `FINAL_WAIT_S`) is closed and logged once (`stt_stream_lost`), and the rest of the call goes by
  request; a turn whose commit it failed is sent as a request of its audio after all.
- **The call's end** (`drop`) closes it (`stt_stream_closed`). No log line holds a word.
"""

from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import Coroutine, Mapping
from dataclasses import dataclass, field
from typing import Any, Final

from pipecat.frames.frames import Frame, VADUserStartedSpeakingFrame, VADUserStoppedSpeakingFrame
from pipecat.services.stt_service import STTService
from pydantic import JsonValue

from t2_agentic_voice.core.clock import Clock
from t2_agentic_voice.core.errors import ProviderError
from t2_agentic_voice.core.logging import get_logger
from t2_agentic_voice.domain.ports.speech_to_text import SpeechToText, Transcript
from t2_agentic_voice.domain.ports.transcript_stream import StreamingSpeechToText, TranscriptStream

log = get_logger(__name__)

LEAD_S: Final = 2.0  # the call heard before a turn is streamed (the module's docstring)
FLUSH_S: Final = 20.0  # the silence after which the call's stream is committed
SPAN_S: Final = 30.0  # the audio since the last commit past which a turn goes by request
FINAL_WAIT_S: Final = 1.5  # the longest a streamed request waits for its words (probe max 825 ms)


class StreamHooks:
    """What the bridge tells its call's stream (the module's docstring); here, nothing."""

    @property
    def ready(self) -> bool:
        """Whether a turn opened now is streamed: never, here."""
        return False

    def saw(self, frame: Frame) -> None:
        """A frame reached the bridge (the detector's start or stop)."""

    def heard(self, audio: bytes, *, in_turn: bool) -> None:
        """The bridge held `audio`, in a turn or not."""

    def opened(self, turn_id: int) -> None:
        """The turn opened."""

    def overlap(self, turn_id: int) -> None:
        """The session marked the open turn an overlap."""

    def closed(self, turn_id: int) -> None:
        """The turn closed, its own request sent."""

    def listen_in(self, language: str | None) -> None:
        """The session named the call's language."""

    async def drop(self) -> None:
        """The call has ended."""


@dataclass(frozen=True)
class Commits:
    """A streamed turn's commits so far (`numbers`), on the `stream` they went to."""

    stream: TranscriptStream
    numbers: tuple[int, ...]


@dataclass
class _Turn:
    stream: TranscriptStream
    commits: list[int] = field(default_factory=list)


def call_stream(
    processor: STTService,
    stt: SpeechToText,
    prompts: Mapping[str, str],
    clock: Clock,
    *,
    on: bool,
    preroll_s: float,
) -> StreamHooks:
    """The call's stream: a `CallStream` on `stt` when `on` and `stt` streams, its turns fed
    from `preroll_s` before they open; else hooks that do nothing."""
    if on and isinstance(stt, StreamingSpeechToText):
        return CallStream(processor, stt, prompts, clock, preroll_s)
    return StreamHooks()


class CallStream(StreamHooks):
    """The stream of the bridge `processor` (its sample rate, its pre-roll `preroll_s`) on
    `provider`, opened with the `prompts` of its language, timed on `clock` (the module's)."""

    def __init__(
        self,
        processor: STTService,
        provider: StreamingSpeechToText,
        prompts: Mapping[str, str],
        clock: Clock,
        preroll_s: float,
    ) -> None:
        self._processor, self._provider, self._preroll_s = processor, provider, preroll_s
        self._prompts, self._clock = dict(prompts), clock
        self._stream: TranscriptStream | None = None
        self._language: str | None = None
        self._opening: asyncio.Task[None] | None = None
        self._tasks: set[asyncio.Task[None]] = set()
        self._lost = self._dropped = False
        self._fed = self._since = 0  # bytes fed to the stream, and since its last commit
        self._speaking = self._spoken = False  # speech heard now, and since the last commit
        self._late: deque[bytes] = deque()  # the audio between turns, held a pre-roll long
        self._turns: dict[int, _Turn] = {}
        self.commits = self.answered = 0

    @property
    def ready(self) -> bool:
        """Whether a turn opened now is streamed: the stream open, hearing, fed `LEAD_S`."""
        stream = self._stream
        return stream is not None and stream.failure is None and self._fed >= self._bytes(LEAD_S)

    def saw(self, frame: Frame) -> None:
        if isinstance(frame, VADUserStartedSpeakingFrame):
            self._speaking = self._spoken = True
        elif isinstance(frame, VADUserStoppedSpeakingFrame):
            self._speaking = False

    def heard(self, audio: bytes, *, in_turn: bool) -> None:
        stream = self._stream
        if stream is None:
            return
        if stream.failure is not None:
            self._lose(stream, stream.failure)
            return
        if in_turn:
            self._feed(stream, audio)
            return
        self._late.append(audio)
        keep = int(self._preroll_s * self._processor.sample_rate) * 2  # as the bridge keeps it
        while sum(map(len, self._late)) - len(self._late[0]) >= keep:
            self._feed(stream, bytes(len(self._late.popleft())))  # no request hears it: silence
        if not self._speaking and self._since >= self._bytes(FLUSH_S):
            self._commit(stream)  # the call's silence, its words dropped

    def opened(self, turn_id: int) -> None:
        stream = self._stream
        if self.ready and stream is not None:
            self._turns[turn_id] = _Turn(stream)
        while self._late and stream is not None:  # the turn's pre-roll, as its request holds it
            self._feed(stream, self._late.popleft())

    def overlap(self, turn_id: int) -> None:
        self._turns.pop(turn_id, None)

    def closed(self, turn_id: int) -> None:
        streamed, stream = self._turns.pop(turn_id, None), self._stream
        if streamed is None and stream is not None and stream.failure is None and self._spoken:
            self._commit(stream)  # a turn heard by request: its words dropped

    def listen_in(self, language: str | None) -> None:
        if self._lost or self._dropped or language == self._language:
            return
        self._language = language
        self._retire()
        if language is not None:
            self._opening = self._spawn(self._open(language))

    def commit(self, turn_id: int) -> Commits | None:
        """Commit the streamed turn's audio since the last commit, unless no speech came since
        its last one; its commits so far, or None when it goes by request (the module's)."""
        turn, stream = self._turns.get(turn_id), self._stream
        if turn is None or stream is None or turn.stream is not stream:
            return None
        if stream.failure is not None:
            return None
        if self._spoken or not turn.commits:
            if self._since >= self._bytes(SPAN_S):
                del self._turns[turn_id]  # by request: its close commits its audio
                return None
            turn.commits.append(self._commit(stream))
        return Commits(stream, tuple(turn.commits))

    async def joined(self, commits: Commits, language: str | None) -> Transcript | None:
        """The turn's words: each of its commits' answer, joined, in `language`, once all came
        within `FINAL_WAIT_S`; None when the stream failed one, the stream then lost."""
        try:
            async with asyncio.timeout(FINAL_WAIT_S):
                heard = [await commits.stream.committed(number) for number in commits.numbers]
        except ProviderError as error:
            self._lose(commits.stream, error)
            return None
        except TimeoutError:
            details: dict[str, JsonValue] = {"error": "no_final"}
            self._lose(commits.stream, ProviderError("timeout", True, details=details))
            return None
        self.answered += 1
        words = " ".join(text for text in (each.text.strip() for each in heard) if text)
        return Transcript(text=words, language=language)

    async def drop(self) -> None:
        if self._dropped:
            return
        self._dropped = True
        self._retire()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        log.info("stt_stream_closed", commits=self.commits, answered=self.answered, lost=self._lost)

    async def _open(self, language: str) -> None:
        started, rate = self._clock.now(), self._processor.sample_rate
        prompt = self._prompts.get(language)
        try:
            stream = await self._provider.open_stream(
                language=language, prompt=prompt, sample_rate=rate
            )
        except Exception as error:  # the provider's failure, or an adapter's bug
            if language == self._language:  # still the call's opening
                self._lose(None, _as_provider_error(error), at="open")
            return
        if self._dropped or self._lost or language != self._language:
            await stream.aclose()
            return
        self._opening, self._late = None, deque()
        # The speech heard so far stays heard: a turn open now is committed at its close.
        self._stream, self._fed, self._since, self._spoken = stream, 0, 0, self._speaking
        connect_ms = round((self._clock.now() - started) * 1000, 1)
        log.info("stt_stream_opened", language=language, connect_ms=connect_ms)

    def _feed(self, stream: TranscriptStream, audio: bytes) -> None:
        stream.feed(audio)
        self._fed += len(audio)
        self._since += len(audio)

    def _commit(self, stream: TranscriptStream) -> int:
        self.commits += 1
        self._since, self._spoken = 0, self._speaking
        return stream.commit()

    def _bytes(self, seconds: float) -> int:
        return round(seconds * self._processor.sample_rate) * 2

    def _lose(
        self, stream: TranscriptStream | None, error: ProviderError, *, at: str = "call"
    ) -> None:
        """The call's stream failed with `error`: closed, logged once, the rest of the call by
        request; a failure of a stream no longer the call's changes nothing."""
        if self._lost or stream is not self._stream:
            return
        self._lost = True
        self._retire()
        reason = error.details.get("error")
        log.warning("stt_stream_lost", at=at, kind=error.kind, reason=reason, commits=self.commits)

    def _retire(self) -> None:
        """The stream closed, and its opening cancelled, in the background; no turn streamed."""
        opening, self._opening = self._opening, None
        if opening is not None and opening is not asyncio.current_task():
            opening.cancel()
        stream, self._stream = self._stream, None
        self._turns.clear()
        if stream is not None:
            self._spawn(stream.aclose())

    def _spawn(self, work: Coroutine[Any, Any, None]) -> asyncio.Task[None]:
        task = asyncio.create_task(work, name="t2v-stt-stream")
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task


def _as_provider_error(error: Exception) -> ProviderError:
    """`error` when it is a ProviderError; an adapter's bug as a server error, by its class."""
    if isinstance(error, ProviderError):
        return error
    details: dict[str, JsonValue] = {"error": type(error).__name__}
    return ProviderError("server_error", False, details=details)
