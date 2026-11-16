"""The day's requests of one key over every app's run history (run_history.py): each app's
history found beside the one given, the day's counts summed over all of them, the other days and
the lines that count nothing left out, and a history the counter cannot read refused by file and
line, never by value."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest
from t2_agentic_voice.evals import RunHistoryError, every_history, requests_today

DAY = date(2026, 11, 7)
SECRET = "gsk_live_do_not_echo"  # a value no refusal may show


def _write(path: Path, *lines: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "".join((line if isinstance(line, str) else json.dumps(line)) + "\n" for line in lines)
    path.write_bytes(text.encode("utf-8"))
    return path


def _line(time: str, requests: object, **more: object) -> dict[str, object]:
    return {"kind": "talker", "time": time, "requests": requests, **more}


def _apps(tmp_path: Path) -> tuple[Path, Path]:
    first = _write(
        tmp_path / "apps" / "first-app" / "evals" / "history.jsonl",
        _line("2026-11-07T09:00:00+00:00", {"openai/gpt-oss-120b": 40, "judge": 10}),
    )
    second = _write(
        tmp_path / "apps" / "second-app" / "evals" / "history.jsonl",
        _line("2026-11-07T13:30:00Z", {"openai/gpt-oss-120b": 25}),
    )
    (tmp_path / "apps" / "no-history" / "evals").mkdir(parents=True)  # an app with no run yet
    return first, second


def test_the_day_counter_sums_every_apps_history(tmp_path: Path) -> None:
    first, second = _apps(tmp_path)
    assert every_history(first) == (first, second)
    assert every_history(second) == (second, first)  # the one given first, then the others
    found = requests_today(every_history(first), DAY)
    assert found == {"openai/gpt-oss-120b": 65, "judge": 10}


def test_a_history_outside_an_apps_folder_is_counted_alone(tmp_path: Path) -> None:
    alone = _write(tmp_path / "runs" / "history.jsonl", _line("2026-11-07T09:00:00+00:00", {}))
    _write(tmp_path / "other" / "runs" / "history.jsonl", _line("2026-11-07T09:00:00Z", {"m": 1}))
    assert every_history(alone) == (alone,)
    assert every_history(tmp_path / "apps" / "history.jsonl") == (
        tmp_path / "apps" / "history.jsonl",
    )


def test_only_the_days_counted_lines_count(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "history.jsonl",
        _line("2026-11-07T00:00:00+00:00", {"m": 1}),
        _line("2026-11-06T23:59:59+00:00", {"m": 100}),  # the day before, in UTC
        _line("2026-11-08T01:00:00+03:00", {"m": 2}),  # Riyadh's 8th is still UTC's 7th
        _line("2026-11-07T12:00:00", {"m": 4}),  # no zone: read as UTC
        _line("2026-11-07T12:00:00+00:00", 7),  # requests counted otherwise: nothing here
        {"kind": "eval", "time": "2026-11-07T12:00:00+00:00"},  # no requests at all
        {"kind": "old"},  # no requests, no time: a line that counts nothing
        "",
    )
    assert requests_today([path], DAY) == {"m": 7}


def test_a_missing_history_counts_nothing_and_a_file_counts_once(tmp_path: Path) -> None:
    path = _write(tmp_path / "history.jsonl", _line("2026-11-07T09:00:00+00:00", {"m": 3}))
    assert requests_today([tmp_path / "none.jsonl"], DAY) == {}
    assert requests_today([path, path, tmp_path / "." / "history.jsonl"], DAY) == {"m": 3}


@pytest.mark.parametrize(
    ("line", "message"),
    [
        (f"not json {SECRET}", "line 2 is not a line of JSON"),
        (json.dumps([SECRET]), "line 2 is not a JSON object"),
        (json.dumps({"requests": {"m": 1}, "note": SECRET}), "line 2 counts requests with no time"),
        (json.dumps(_line(SECRET, {"m": 1})), "line 2: its time is not an ISO 8601 time"),
        (json.dumps(_line("2026-11-07T09:00:00Z", {"m": -1})), "not a whole number >= 0"),
        (json.dumps(_line("2026-11-07T09:00:00Z", {"m": True})), "not a whole number >= 0"),
        (json.dumps(_line("2026-11-07T09:00:00Z", {"m": SECRET})), "not a whole number >= 0"),
    ],
)
def test_a_history_the_counter_cannot_read_is_refused_by_file_and_line(
    tmp_path: Path, line: str, message: str
) -> None:
    """Adversarial: a broken line would undercount the day, so it stops the run before anything
    is sent; the refusal names the file and the line, and never shows what the line held."""
    path = _write(tmp_path / "history.jsonl", _line("2026-11-07T09:00:00Z", {"m": 1}), line)
    with pytest.raises(RunHistoryError, match=message) as refused:
        requests_today([path], DAY)
    assert str(path) in str(refused.value) and SECRET not in str(refused.value)
    assert refused.value.code == "run_history"


def test_a_history_that_is_not_utf8_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "history.jsonl"
    path.write_bytes(b'{"time": "\xff"}\n')
    with pytest.raises(RunHistoryError, match="not a readable UTF-8 file"):
        requests_today([path], DAY)
