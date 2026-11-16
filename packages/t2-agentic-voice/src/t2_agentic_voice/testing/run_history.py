"""The day's requests of a provider key, counted over every app's run history: the apps of one
repository spend on one key, so a run starts its pacers' day (`ModelPacer`'s `used_today`) from
the requests every app's runs sent that day, and no run stops part way for a limit it did not see.

A run history is a file of JSON lines, one per run or session, each app's in its own shape. What
the counter reads of a line is two fields: `requests`, an object of each model's requests, and
`time`, when the run began (ISO 8601; a time with no zone is read as UTC). A line with no
`requests` object counts nothing (a run that sends no chat request, or counts it otherwise); a
line with one counts on the UTC day its `time` falls on. A file that is not UTF-8, a line that is
not a JSON object, or a counted line with no valid `time` or with a count that is not a whole
number of 0 or more is a `RunHistoryError` naming the file and the line, never a value: a history
the counter cannot read would undercount the day. A file that does not exist counts nothing.

`every_history` finds the histories to count: given one app's, at `<apps>/<app>/<path>` under a
folder named `apps`, each app's at the same `<path>`. Public through the `evals` facade.
"""

from __future__ import annotations

import json
from collections import Counter
from collections.abc import Iterable
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Final

from t2_agentic_voice.core.errors import T2VoiceError

APPS: Final = "apps"  # the folder each app of a repository sits in


class RunHistoryError(T2VoiceError):
    """A run history the day's counter cannot read; the message names the file and the line,
    never a value."""

    code = "run_history"


def every_history(history: Path) -> tuple[Path, ...]:
    """`history`, then every other app's history at the same place: when `history` is
    `<apps>/<app>/<path>` under the nearest folder named `apps`, each `<apps>/*/<path>` that is
    a file, in name order; `history` alone when no folder above it is named `apps`."""
    for folder in history.parents:
        if folder.name == APPS and folder != history.parent:
            rest = history.relative_to(folder).parts[1:]
            others = sorted(
                found
                for app in folder.iterdir()
                if app.is_dir() and (found := app.joinpath(*rest)).is_file()
            )
            return (history, *(other for other in others if other != history))
    return (history,)


def requests_today(histories: Iterable[Path], today: date) -> Counter[str]:
    """Each model's requests in the lines of `histories` whose run began on `today` (UTC), each
    file counted once (the module's docstring)."""
    found: Counter[str] = Counter()
    seen: set[Path] = set()
    for history in histories:
        key = history.resolve()
        if key in seen or not history.exists():
            continue
        seen.add(key)
        found.update(_counted(history, today))
    return found


def _counted(history: Path, today: date) -> Counter[str]:
    try:
        text = history.read_bytes().decode("utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise RunHistoryError(f"{history} is not a readable UTF-8 file") from error
    found: Counter[str] = Counter()
    for number, raw in enumerate(text.splitlines(), start=1):
        if not raw.strip():
            continue
        where = f"{history}, line {number}"
        try:
            line = json.loads(raw)
        except json.JSONDecodeError as error:
            raise RunHistoryError(f"{where} is not a line of JSON") from error
        if not isinstance(line, dict):
            raise RunHistoryError(f"{where} is not a JSON object")
        requests = line.get("requests")
        if not isinstance(requests, dict):
            continue
        if _day(line.get("time"), where) != today:
            continue
        for model, count in requests.items():
            if isinstance(count, bool) or not isinstance(count, int) or count < 0:
                raise RunHistoryError(f"{where}: a model's requests are not a whole number >= 0")
            found[str(model)] += count
    return found


def _day(value: object, where: str) -> date:
    """The UTC day of a line's `time`."""
    if not isinstance(value, str):
        raise RunHistoryError(f"{where} counts requests with no time")
    try:
        when = datetime.fromisoformat(value)
    except ValueError as error:
        raise RunHistoryError(f"{where}: its time is not an ISO 8601 time") from error
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    return when.astimezone(UTC).date()
