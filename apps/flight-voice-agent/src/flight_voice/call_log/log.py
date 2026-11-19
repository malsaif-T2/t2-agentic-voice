"""The call log (`CallLog`): every call of the server kept in the database (store.py), for the
alpha's learning, debugging and complaints (the owner, 2026-11-19: "keep all the relevant data we
can gather from each call ... so we can learn and improve it later, or debug any problems").

It observes every event the runtime emits (`observe`, registered for `Event`):

- `CallStarted` makes the call's row, with the setup the server runs (`setup`: the agent and its
  version, the flight data's source, the models, the speech-to-text, the voice, the register held,
  the release), so a call is read with what answered it.
- Every event is kept whole in `events`; a finished tool call in `tool_calls` too.
- `CallEnded` closes the row: its end, why, the consent version, the turns, the whole report,
  each turn in `turns`, and the recording's folder when the library kept the call's audio
  (`recordings/<call ID>/`: `caller.wav`, `agent.wav`, `timeline.jsonl`; on when
  `privacy.record_audio` is on and the caller's token consented).

Nothing is logged of the calls' content; the database sits under the storage folder (`var/`,
never committed).
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Final

from pydantic import JsonValue
from t2_agentic_voice.events import CallEnded, CallStarted, Event, ToolFinished

from flight_voice.call_log.store import CallStore, Row

__all__ = ["RECORDINGS", "CallLog"]

# The library's recordings folder under the storage folder (voice/session/recording.py).
RECORDINGS: Final = "recordings"


class CallLog:
    """The log of the server's calls into `store`, each with `setup`, its recordings looked for
    under `var_dir` (the module's docstring)."""

    def __init__(self, store: CallStore, setup: dict[str, JsonValue], var_dir: Path) -> None:
        self.store, self.setup, self.var_dir = store, setup, var_dir

    async def observe(self, event: Event) -> None:
        """Keep `event` (the module's docstring); never raises into the call."""
        rows: list[Row] = []
        if isinstance(event, CallStarted):
            rows.append(
                (
                    "INSERT OR IGNORE INTO calls (call_id, started_at, setup) VALUES (?, ?, ?)",
                    (event.call_id, event.at.isoformat(), json.dumps(self.setup)),
                )
            )
        rows.append(
            (
                "INSERT INTO events (call_id, turn_id, at, type, payload) VALUES (?, ?, ?, ?, ?)",
                (
                    event.call_id,
                    event.turn_id,
                    event.at.isoformat(),
                    type(event).__name__,
                    event.model_dump_json(),
                ),
            )
        )
        if isinstance(event, ToolFinished):
            rows.append(_tool(event))
        if isinstance(event, CallEnded):
            rows += self._ended(event)
        self.store.put(*rows)

    def _ended(self, event: CallEnded) -> list[Row]:
        report = event.report
        recording = Path(RECORDINGS) / event.call_id
        kept = (self.var_dir / recording).is_dir()
        rows: list[Row] = [
            (
                "INSERT OR IGNORE INTO calls (call_id, started_at, setup) VALUES (?, ?, ?)",
                (event.call_id, report.started_at.isoformat(), json.dumps(self.setup)),
            ),
            (
                "UPDATE calls SET ended_at = ?, ended_by = ?, agent = ?, consent_version = ?, "
                "turns = ?, recording = ?, report = ? WHERE call_id = ?",
                (
                    report.ended_at.isoformat(),
                    report.ended_by,
                    report.agent,
                    report.consent_version,
                    len(report.turns),
                    recording.as_posix() if kept else None,
                    report.model_dump_json(),
                    event.call_id,
                ),
            ),
        ]
        for turn in report.turns:
            times = turn.times
            rows.append(
                (
                    "INSERT OR REPLACE INTO turns (call_id, turn_id, language, heard, said, "
                    "dropped, stopped, ttfa_ms, stt_ms, llm_first_token_ms, tts_first_audio_ms, "
                    "end_of_turn_ms, times) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        event.call_id,
                        turn.turn_id,
                        turn.language,
                        turn.heard,
                        turn.said,
                        int(turn.dropped),
                        int(turn.stopped),
                        times.ttfa_ms,
                        times.stt_ms,
                        times.llm_first_token_ms,
                        times.tts_first_audio_ms,
                        times.end_of_turn_ms,
                        times.model_dump_json(),
                    ),
                )
            )
        return rows

    async def aclose(self) -> None:
        """Write what is queued, then stop the store's thread (the app's lifespan)."""
        await asyncio.to_thread(self.store.close)


def _tool(event: ToolFinished) -> Row:
    return (
        "INSERT INTO tool_calls (call_id, turn_id, at, tool, tool_call_id, arguments, result, ok, "
        "ms, failure) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            event.call_id,
            event.turn_id,
            event.at.isoformat(),
            event.tool,
            event.tool_call_id,
            event.arguments,
            event.result,
            int(event.ok),
            event.ms,
            event.failure,
        ),
    )
