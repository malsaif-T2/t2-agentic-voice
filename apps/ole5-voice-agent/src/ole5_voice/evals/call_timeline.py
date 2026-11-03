"""A recorded call's timeline and caller's track, as the import of its overlaps reads them
(import_calls.py; voice/session/recording.py writes them): each line of `timeline.jsonl`, the
caller's track once its alignment is checked (TD-070), and each turn whose speech began over a
reply or in its tail (`overlaps`).

**The alignment** (TD-070): the recorder pads each track by its taps' times, so a tap delivered
late puts silence in the track and shifts the rest of it later, and the shift shows at its end as
a caller's track longer than the call. A caller's track that runs past the timeline's `ended`
line by more than `ALIGN_TOLERANCE_S`, or a call with no `ended` line, is refused.

**The overlaps**: a reply plays from its first clause's first audio queued to its last clause's
end (played, failed, or dropped by a stop); a turn whose speech began while it played, or within
`TAIL_S` after its last clause played (D-037; none after a stop), is an overlap of the latest such
reply, and the texts that played over it are those of the reply's clauses whose play met the
turn's speech, or, for a turn in the tail, the reply's last clause.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Final

from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

from ole5_voice.evals.audio import AudioFormatError, read_wav
from ole5_voice.evals.files import read_text
from ole5_voice.evals.items import GoldenSetError

ALIGN_TOLERANCE_S: Final = 0.1  # how far past the call a caller's track may run (the agent's)
TAIL_S: Final = 0.3  # D-037: a turn this soon after a reply's last clause played is an overlap


class TimelineLine(BaseModel):
    """A line of a call's `timeline.jsonl`: the fields the import reads; it ignores the rest."""

    model_config = ConfigDict(frozen=True, extra="ignore", hide_input_in_errors=True)

    t: float = Field(allow_inf_nan=False)
    event: str
    turn_id: int | None = None
    reply_id: int | None = None
    clause: int | None = None
    replies: tuple[int, ...] = ()
    speech_s: float | None = None
    speech_ended_s: float | None = None
    text: str | None = None


_TIMELINE_LINE: Final = TypeAdapter(TimelineLine)


@dataclass(frozen=True)
class Overlap:
    """One turn over a reply: its turn, when its speech began and stopped (seconds from the
    call's start), and the texts that played over it."""

    turn: int
    speech_s: float
    stopped_s: float
    reply: tuple[str, ...]


def timeline(folder: Path) -> list[TimelineLine]:
    """A call's timeline, each line checked; GoldenSetError naming the line otherwise."""
    text = read_text(folder / "timeline.jsonl")
    if text is None:
        raise GoldenSetError(f"{folder.name}: no readable timeline.jsonl")
    lines = []
    for number, raw in enumerate(text.splitlines(), start=1):
        try:
            lines.append(_TIMELINE_LINE.validate_json(raw))
        except ValueError:  # a pydantic ValidationError, which never echoes the line
            raise GoldenSetError(f"{folder.name}: timeline line {number} cannot be read") from None
    return lines


def check_alignment(folder: Path, lines: Sequence[TimelineLine]) -> bytes:
    """The caller's track, once it ends within `ALIGN_TOLERANCE_S` of the call's `ended` line;
    GoldenSetError otherwise (TD-070)."""
    ended = next((line.t for line in lines if line.event == "ended"), None)
    if ended is None:
        raise GoldenSetError(f"{folder.name}: the call has no ended line")
    try:
        caller = read_wav(folder / "caller.wav")
    except (OSError, AudioFormatError) as error:
        raise GoldenSetError(f"{folder.name}: caller.wav: {error}") from None
    if caller.seconds > ended + ALIGN_TOLERANCE_S:
        late = caller.seconds - ended
        raise GoldenSetError(f"{folder.name}: its caller's track runs {late:.2f} s past the call")
    return caller.pcm16


# A clause's play: when its first audio was queued, when it ended, and whether it played whole.
_Play = tuple[float, float, bool]


def overlaps(lines: Sequence[TimelineLine]) -> list[Overlap]:
    """Each turn of a call's timeline whose speech began over a reply or in its tail, in the
    order the turns opened."""
    asked: dict[tuple[int, int], str] = {}
    begun: dict[tuple[int, int], float] = {}
    ended: dict[tuple[int, int], tuple[float, bool]] = {}
    for line in lines:
        key = (line.reply_id or 0, line.clause or 0)
        if line.event == "clause_asked":
            asked[key] = line.text or ""
        elif line.event == "clause_queued":
            begun.setdefault(key, line.t)
        elif line.event in ("clause_played", "clause_failed"):
            ended.setdefault(key, (line.t, line.event == "clause_played"))
        elif line.event == "stopped":
            for dropped in begun.keys() - ended.keys():
                if dropped[0] in line.replies:
                    ended[dropped] = (line.t, False)
    last = max((line.t for line in lines), default=0.0)
    plays: dict[int, dict[int, _Play]] = {}
    for (reply, clause), start in begun.items():
        plays.setdefault(reply, {})[clause] = (start, *ended.get((reply, clause), (last, False)))
    closed = {line.turn_id: line.speech_ended_s for line in lines if line.event == "turn_closed"}
    found = []
    for line in lines:
        if line.event == "turn_opened" and line.turn_id is not None and line.speech_s is not None:
            stopped = closed.get(line.turn_id)
            stopped = last if stopped is None else stopped
            over = _over(plays, asked, line.speech_s, stopped)
            if over is not None:
                found.append(Overlap(line.turn_id, line.speech_s, stopped, over))
    return found


def _over(
    plays: dict[int, dict[int, _Play]],
    asked: dict[tuple[int, int], str],
    speech: float,
    stopped: float,
) -> tuple[str, ...] | None:
    """The texts of the latest reply the speech began over, or in the tail of: its clauses whose
    play met the speech, or its last clause for a turn in its tail; None for no reply."""
    for reply in sorted(plays, reverse=True):
        clauses = plays[reply]
        start = min(play[0] for play in clauses.values())
        end, played = max((play[1], play[2]) for play in clauses.values())
        if not start <= speech <= end + (TAIL_S if played else 0.0):
            continue
        met = [n for n, (s, e, _) in sorted(clauses.items()) if s <= stopped and e >= speech]
        texts = (asked.get((reply, n), "") for n in met or [max(clauses)])
        return tuple(text for text in texts if text)
    return None
