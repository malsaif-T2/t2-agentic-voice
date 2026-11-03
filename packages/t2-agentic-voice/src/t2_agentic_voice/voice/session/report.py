"""What one call reports (core/events.py; the design's 6.6): its turns as the session keeps them,
its public events (`CallEvents`), and its `CallReport`: what was heard and said in each turn and
when each step happened, the usage per model, and the browser's view of the connection.

The report holds what was heard and said, so it goes only to the team's observers (`CallEnded`).
Its numbers, with no text of the call (no heard or said words), go into a JSON file per call,
`<call ID>.json` under `storage.var_dir`'s `reports/` (`write_report`), and onto the call's root
span (`span_attributes`), never into a log line (the design's 10.2).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from pydantic import JsonValue, ValidationError

from t2_agentic_voice.core.errors import ProviderErrorKind
from t2_agentic_voice.core.events import (
    AgentSpeechEnded,
    CallEnded,
    CallReport,
    CallStarted,
    ClientConnection,
    EndReason,
    Interrupted,
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
from t2_agentic_voice.core.settings.tts import LanguageTag
from t2_agentic_voice.voice.protocol import ClientStats, ReplyId
from t2_agentic_voice.voice.session.io import CallSetup

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
    """One of the caller's turns as the session keeps it: when it began, when its speech ended
    and its transcript came, what was heard and said back, the reply that answers it, and how
    it ended. `answered` turns are said back; a `dropped` one began over the agent's speech."""

    turn_id: TurnId
    speech_at: float | None = None
    closed: bool = False
    speech_ended_at: float | None = None
    requested: bool = False
    transcribed_at: float | None = None
    heard: str = ""
    said: str = ""
    dropped: bool = False
    stopped: bool = False
    unfinished: bool = False
    reply_id: ReplyId | None = None
    first_audio_at: float | None = None
    tts_first_audio_s: float | None = None
    done: bool = False

    @property
    def transcribed(self) -> bool:
        return self.transcribed_at is not None

    @property
    def awaited(self) -> bool:
        """Whether the turn has closed, is to be answered, and its transcript has not come."""
        return self.closed and not self.dropped and not self.transcribed

    def times(self) -> TurnTimes:
        """How long its steps took, from the end of the caller's speech: to the transcript (when
        a request went), to the reply's first audio, and the reply's first request to its first
        audio."""
        end = self.speech_ended_at
        tts_ms = None if self.tts_first_audio_s is None else self.tts_first_audio_s * 1000
        return TurnTimes(
            stt_ms=_ms(self.transcribed_at, end) if self.requested else None,
            ttfa_ms=_ms(self.first_audio_at, end),
            tts_first_audio_ms=tts_ms,
        )

    def record(self, language: LanguageTag) -> TurnRecord:
        return TurnRecord(
            turn_id=self.turn_id,
            language=language,
            heard=self.heard,
            said=self.said,
            dropped=self.dropped,
            stopped=self.stopped,
            unfinished=self.unfinished,
            times=self.times(),
        )

    def outcome(self) -> dict[str, str | bool | int | float]:
        """Its outcome and times as span attributes: no text."""
        found: dict[str, str | bool | int | float] = {
            "turn.dropped": self.dropped,
            "turn.stopped": self.stopped,
            "turn.unfinished": self.unfinished,
        }
        times = self.times().model_dump(exclude_none=True)
        found |= {f"turn.{name}": value for name, value in times.items()}
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
    language = setup.language.tag
    return CallReport(
        call_id=setup.call_id,
        agent=setup.agent.name,
        started_at=started_at,
        ended_at=max(ended_at, started_at),
        ended_by=ended_by,
        consent_version=setup.consent.version,
        turns=tuple(turn.record(language) for turn in sorted(turns, key=lambda t: t.turn_id)),
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

    def heard(self, turn_id: TurnId, heard: str) -> None:
        self._emit(
            UserTurnEnded(call_id=self._id, turn_id=turn_id, at=self._clock.wall(), heard=heard)
        )

    def metrics(self, turn: TurnLog) -> None:
        times = turn.times().model_dump()
        at = self._clock.wall()
        self._emit(TurnMetrics(call_id=self._id, turn_id=turn.turn_id, at=at, **times))

    def spoke(self, turn_id: TurnId | None, text: str, played: float) -> None:
        at = self._clock.wall()
        ended = AgentSpeechEnded(
            call_id=self._id, turn_id=turn_id, at=at, text=text, played_fraction=played
        )
        self._emit(ended)

    def stopped(self, turn_id: TurnId | None) -> None:
        self._emit(
            Interrupted(call_id=self._id, turn_id=turn_id, at=self._clock.wall(), kind="stop")
        )

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
