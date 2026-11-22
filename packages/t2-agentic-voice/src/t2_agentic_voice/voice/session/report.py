"""What one call reports (core/events.py; the design's 6.6): its turns as the session keeps them,
its public events (`CallEvents`), and its `CallReport`: what was heard and said in each turn and
when each step happened, the usage per model, and the browser's view of the connection.

The report holds what was heard and said, so it goes only to the team's observers (`CallEnded`).
Its numbers, with no text of the call (no heard or said words), go into a JSON file per call,
`<call ID>.json` under `storage.var_dir`'s `reports/` (`write_report`), and onto the call's root
span (`span_attributes`), never into a log line (the design's 10.2).
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from pydantic import JsonValue, ValidationError

from t2_agentic_voice.agent.language import tag_of
from t2_agentic_voice.core.conversation import TurnFate
from t2_agentic_voice.core.errors import ProviderErrorKind
from t2_agentic_voice.core.events import (
    AgentSpeechEnded,
    CallEnded,
    CallReport,
    CallStarted,
    ClientConnection,
    EndReason,
    Interrupted,
    InterruptionKind,
    InterruptionReason,
    LanguageBy,
    ModelUsage,
    ProviderFailed,
    TransportFailed,
    TransportStage,
    TurnId,
    TurnMetrics,
    TurnRecord,
    TurnTimes,
    UserTurnEnded,
)
from t2_agentic_voice.core.logging import get_logger
from t2_agentic_voice.core.settings.tts import LanguageTag
from t2_agentic_voice.core.tracing_tts import CallTrace
from t2_agentic_voice.voice.protocol import ClientStats, ReplyId
from t2_agentic_voice.voice.session.io import CallSetup

_log = get_logger(__name__)

# The folder under `storage.var_dir` that holds each call's report file.
REPORTS = "reports"
# The turn records' fields that hold the call's words, which the file and the spans never hold.
_WORDS = {"heard", "said"}


def _ms(later: float | None, earlier: float | None) -> float | None:
    """From `earlier` to `later`, in milliseconds, never below 0; None when either is unknown."""
    if later is None or earlier is None:
        return None
    return max(0.0, later - earlier) * 1000


@dataclass(kw_only=True)
class TurnLog:
    """One of the caller's turns as the session keeps it: when it began, when its speech ended (as
    the detector's stop came, `stop_delay_s` after the speech's true end), when Smart Turn
    called it complete (`complete_at`, as its hold began) and when it closed, when its
    transcript came (and its `held` request's, `held_heard_at`, which a turn whose speech did
    not go on takes as its own: plan 006's early start), what was heard and what the caller
    heard said back (the heard history's), the reply that answers it, and how it ended (`fate`,
    the heard history's). A `dropped` one began over the agent's speech under
    `interruptions.mode = "drop"`, an `overlap` under `two_step` (overlap.py), over the reply
    `over_reply`; `cut_reply` is the reply its words stopped. Its reply's first audio (queued,
    and the first audible frame sent once the output taps any: `audio_seen`), its first progress
    line's apart, the browser's playback of it, and the chat model's first token are its times'
    ends. While a chat model's word on its answer to a read-back is awaited (yes_ask.py) it is
    `judging`: neither answered nor settled yet. `stray_characters` counts the characters the
    stray-script filter took out of, or rewrote in, what its reply's model requests wrote, and
    `stray_scripts` labels their kinds (agent/stray_script.py), never a character. `language`,
    `language_by` and `language_share` are what its first request named, how, and the verdict's
    best share, from its first `Transcribing`, whatever its part, as
    turn_book.py keeps them. `reply_language`: the tag its talker's reply began in (talking.py),
    and `spoken_languages` each tag its clauses were said in, each once, in order
    (talker_play.py). `warm_connection`: whether its first chat request went out on a
    kept-alive connection, None when the model does not say (talker_play.py)."""

    turn_id: TurnId
    speech_at: float | None = None
    closed: bool = False
    speech_ended_at: float | None = None
    complete_at: float | None = None
    closed_at: float | None = None
    held_heard_at: float | None = None
    requested: bool = False
    transcribed_at: float | None = None
    heard: str = ""
    said: str = ""
    dropped: bool = False
    overlap: bool = False
    stopped: bool = False
    unfinished: bool = False
    fate: TurnFate = "pending"
    reply_id: ReplyId | None = None
    over_reply: ReplyId | None = None
    cut_reply: ReplyId | None = None
    stop_delay_s: float = 0.0
    first_audio_at: float | None = None
    first_audible_at: float | None = None
    progress_at: float | None = None
    progress_audible_at: float | None = None
    audio_seen: bool = False
    played_at: float | None = None
    first_token_at: float | None = None
    tts_first_audio_s: float | None = None
    judging: bool = False
    done: bool = False
    stray_characters: int = 0
    stray_scripts: tuple[str, ...] = ()
    language: str | None = None
    language_by: LanguageBy | None = None
    language_share: float | None = None
    reply_language: LanguageTag | None = None
    spoken_languages: tuple[LanguageTag, ...] = ()
    warm_connection: bool | None = None

    @property
    def transcribed(self) -> bool:
        return self.transcribed_at is not None

    @property
    def spoken_at(self) -> float | None:
        """When the caller's speech ended: the detector's stop less its delay."""
        end = self.speech_ended_at
        return None if end is None else end - self.stop_delay_s

    @property
    def awaited(self) -> bool:
        """Whether the turn has closed, is to be answered (not dropped, nor taken by an
        overlap's verdict as a command or let go on), and its transcript has not come."""
        answered = not self.dropped and self.fate == "pending"
        return self.closed and answered and not self.transcribed

    def times(self) -> TurnTimes:
        """How long its steps took (core/events.py's `TurnTimes`): from the end of the caller's
        speech, the detector's stop less its delay, to the reply's first audible frame (its
        first audio queued when the output tapped none), to its first progress line's, to the
        browser's playback, to the chat model's first token, to the turn's close and to Smart
        Turn's "complete"; from the detector's stop as it came to the transcript (when a request
        went, or its `held` request's that it took as its own); and the reply's first request to
        its first audio."""
        end = self.speech_ended_at
        spoken = self.spoken_at
        tts_ms = None if self.tts_first_audio_s is None else self.tts_first_audio_s * 1000
        heard = self.first_audible_at if self.audio_seen else self.first_audio_at
        progress = self.progress_audible_at if self.audio_seen else self.progress_at
        return TurnTimes(
            stt_ms=_ms(self.transcribed_at if self.requested else self.held_heard_at, end),
            ttfa_ms=_ms(heard, spoken),
            llm_first_token_ms=_ms(self.first_token_at, spoken),
            tts_first_audio_ms=tts_ms,
            progress_ms=_ms(progress, spoken),
            played_ms=_ms(self.played_at, spoken),
            end_of_turn_ms=_ms(self.closed_at, spoken),
            turn_complete_ms=_ms(self.complete_at, spoken),
        )

    def record(self, language: LanguageTag, spoken: Sequence[LanguageTag] = ()) -> TurnRecord:
        """Its record in the report of a call held in `language` by an agent that speaks
        `spoken`: the tag of the language its request was sent in (agent/language.py's
        `tag_of`), the call's when none was named, beside its reply's."""
        return TurnRecord(
            turn_id=self.turn_id,
            language=tag_of(self.language, call=language, spoken=spoken),
            language_by=self.language_by or "session",
            reply_language=self.reply_language,
            spoken_languages=self.spoken_languages,
            heard=self.heard,
            said=self.said,
            dropped=self.dropped,
            stopped=self.stopped,
            unfinished=self.unfinished,
            warm_connection=self.warm_connection,
            times=self.times(),
        )

    def outcome(self) -> dict[str, str | bool | int | float]:
        """Its outcome and times as span attributes: no text. A turn whose reply lost a
        character to the stray-script filter says how many and their labels, comma-separated; one
        whose first chat request's model says, whether it went out on a warm connection."""
        found: dict[str, str | bool | int | float] = {
            "turn.dropped": self.dropped,
            "turn.stopped": self.stopped,
            "turn.unfinished": self.unfinished,
        }
        times = self.times().model_dump(exclude_none=True)
        found |= {f"turn.{name}": value for name, value in times.items()}
        if self.warm_connection is not None:
            found["turn.warm_connection"] = self.warm_connection
        if self.stray_characters:
            found["turn.stray_characters"] = self.stray_characters
            found["turn.stray_scripts"] = ",".join(self.stray_scripts)
        if self.language_by not in (None, "session"):
            found["turn.language_by"] = self.language_by
            if self.language is not None:
                found["turn.language"] = self.language
        return found


def call_report(
    setup: CallSetup,
    *,
    started_at: datetime,
    ended_at: datetime,
    ended_by: EndReason,
    turns: list[TurnLog],
    usage: tuple[ModelUsage, ...],
    client: ClientConnection | None,
) -> CallReport:
    """The call's report; it ends no earlier than it started, whatever the wall clock did."""
    language, spoken = setup.language.tag, [each.tag for each in setup.agent.languages]
    return CallReport(
        call_id=setup.call_id,
        agent=setup.agent.name,
        started_at=started_at,
        ended_at=max(ended_at, started_at),
        ended_by=ended_by,
        consent_version=setup.consent.version,
        turns=tuple(
            turn.record(language, spoken) for turn in sorted(turns, key=lambda t: t.turn_id)
        ),
        usage=usage,
        client=client,
    )


def merged(client: ClientConnection | None, stats: ClientStats) -> ClientConnection:
    """The browser's view of its connection, its `client_stats` merged into what it said
    before, each value it gives replacing the last; a picture that contradicts the last (a relay
    become a host) is taken alone."""
    given = stats.model_dump(exclude={"v", "type"}, exclude_none=True)
    known = {} if client is None else client.model_dump(exclude_none=True)
    try:
        return ClientConnection.model_validate(known | given)
    except ValidationError:
        return ClientConnection.model_validate(given)


class CallEvents:
    """One call's public events (core/events.py), each stamped with the call's ID and the time
    of day on its clock, handed to where the runtime's observers take them (`CallSetup.emit`,
    which returns at once and never raises). It is the only sender of a `ProviderFailed` or a
    `TransportFailed` for a failure the session is handed (a turn's failed `Transcribed`, a
    clause's `ClauseFailed`, the call's `TransportFailure`: io.py's failures); voice's Pipecat
    side sends only a speech bridge's error frame's (voice/pipecat_events.py)."""

    def __init__(self, setup: CallSetup) -> None:
        self._emit, self._id, self._clock = setup.emit, setup.call_id, setup.clock

    def started(self) -> datetime:
        """The call connected: `CallStarted`; when, as a time of day."""
        at = self._clock.wall()
        self._emit(CallStarted(call_id=self._id, at=at))
        return at

    def heard(self, turn_id: TurnId, heard: str, played: str | None = None) -> None:
        at = self._clock.wall()
        ended = UserTurnEnded(
            call_id=self._id, turn_id=turn_id, at=at, heard=heard, reply_played=played
        )
        self._emit(ended)

    def metrics(self, turn: TurnLog, usage: tuple[ModelUsage, ...] = ()) -> None:
        """The turn settled: its `TurnMetrics`, with each model's `usage` in the call so far."""
        times = turn.times().model_dump()
        at = self._clock.wall()
        metrics = TurnMetrics(call_id=self._id, turn_id=turn.turn_id, at=at, usage=usage, **times)
        self._emit(metrics)

    def spoke(self, turn_id: TurnId | None, text: str, played: float) -> None:
        at = self._clock.wall()
        ended = AgentSpeechEnded(
            call_id=self._id, turn_id=turn_id, at=at, text=text, played_fraction=played
        )
        self._emit(ended)

    def interrupted(
        self,
        turn_id: TurnId | None,
        kind: InterruptionKind = "stop",
        reason: InterruptionReason | None = None,
    ) -> None:
        """The reply answering `turn_id` was interrupted, of `kind`, as the rule decided
        (`reason`; none for the caller's `stop`): its `Interrupted`."""
        at = self._clock.wall()
        self._emit(Interrupted(call_id=self._id, turn_id=turn_id, at=at, kind=kind, reason=reason))

    def failed(self, kind: ProviderErrorKind, retryable: bool, turn_id: TurnId | None) -> None:
        """A request failed, a turn's or a clause's: its `ProviderFailed`, naming `turn_id`."""
        at = self._clock.wall()
        self._emit(
            ProviderFailed(call_id=self._id, turn_id=turn_id, at=at, kind=kind, retryable=retryable)
        )

    def transport(self, stage: TransportStage) -> None:
        """The call's connection failed at `stage`: its `TransportFailed`."""
        self._emit(TransportFailed(call_id=self._id, at=self._clock.wall(), stage=stage))

    def ended(self, report: CallReport) -> None:
        self._emit(CallEnded(call_id=self._id, at=self._clock.wall(), report=report))


def numbers(report: CallReport) -> dict[str, JsonValue]:
    """The report with no text of the call: every turn without what was heard and said, with
    the call's length and each model's requests per call minute."""
    found: dict[str, JsonValue] = report.model_dump(
        mode="json", exclude={"turns": {"__all__": _WORDS}}
    )
    found["duration_s"] = report.duration_s
    rates: dict[str, JsonValue] = {}
    rates.update(report.requests_per_minute())
    found["requests_per_minute"] = rates
    return found


def span_attributes(report: CallReport) -> dict[str, str | bool | int | float]:
    """The report's numbers as the call's root span carries them: how it ended and lasted, its
    turns counted by outcome, each model's usage and requests per call minute, and the
    browser's view of the connection. No text of the call."""
    turns = report.turns
    found: dict[str, str | bool | int | float] = {
        "call.ended_by": report.ended_by,
        "call.duration_s": report.duration_s,
        "call.turns": len(turns),
        "call.turns_dropped": sum(turn.dropped for turn in turns),
        "call.turns_stopped": sum(turn.stopped for turn in turns),
        "call.turns_unfinished": sum(turn.unfinished for turn in turns),
    }
    rates = report.requests_per_minute()
    for usage in report.usage:
        counts = usage.model_dump(exclude={"model"}, exclude_none=True)
        found |= {f"usage.{usage.model}.{name}": value for name, value in counts.items()}
        found[f"usage.{usage.model}.requests_per_minute"] = rates[usage.model]
    if report.client is not None:
        client = report.client.model_dump(exclude_none=True)
        found |= {f"client.{name}": value for name, value in client.items()}
    return found


def write_report(report: CallReport, var_dir: Path) -> Path:
    """Write the report's numbers (`numbers`), with no text of the call, to its file under
    `var_dir`, whole: to a temporary name first, then renamed over it. Returns the file."""
    folder = var_dir / REPORTS
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{report.call_id}.json"
    temporary = folder / f"{report.call_id}.json.tmp"
    text = json.dumps(numbers(report), ensure_ascii=False, indent=2) + "\n"
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)
    return path


async def file_report(
    report: CallReport, setup: CallSetup, *, trace: CallTrace, events: CallEvents
) -> None:
    """The call's report filed once its stream ended: its numbers on the call's root span and in
    its file (a file that cannot be written is logged by the failure's kind alone), then
    `CallEnded` to the observers."""
    trace.close(span_attributes(report))
    try:
        await asyncio.to_thread(write_report, report, setup.settings.storage.var_dir)
    except OSError as error:
        failure = type(error).__qualname__
        _log.warning("report_not_written", call_id=setup.call_id, failure=failure)
    events.ended(report)
